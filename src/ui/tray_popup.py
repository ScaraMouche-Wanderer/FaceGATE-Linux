"""
FaceGate Modern Quick Settings Tray Popup & Control Center

Provides an accessible, GNOME/Quick-Settings style interactive control center
for the system tray, featuring:
- Monochrome vector line glyphs (white/grey) matching modern desktop environments
- Master protection toggle with animated pill switch
- Quick Relock All and Quick Scan actions
- Pause duration stepper and quick preset chips (5m, 15m, 30m, 1h)
- Protected apps quick cards with one-click Unlock / Relock / Launch
- Settings, Enrollment, and Preferences shortcuts
- Intelligent screen-edge and multi-monitor positioning
- Full keyboard navigation and dark/light theme awareness
"""

import os
import shutil
import subprocess
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGraphicsDropShadowEffect, QApplication, QSizePolicy,
    QComboBox
)
from PySide6.QtCore import (
    Qt, QRect, QRectF, QPoint, QPointF, QSize, Signal, Slot, QTimer,
    QPropertyAnimation, QEasingCurve, Property, QEvent
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QIcon, QPixmap, QFont,
    QKeyEvent, QMouseEvent, QCursor, QGuiApplication, QPainterPath
)

from ui.theme import (
    get_colors, resolve_app_icon, composite_tray_icon,
    create_monochrome_icon, create_monochrome_pixmap,
    ACCENT_PURPLE, TEXT_PRIMARY, TEXT_SECONDARY, SUCCESS_GREEN, DANGER_RED, WARNING_AMBER
)


class ModernToggleSwitch(QWidget):
    """
    Sleek, animated iOS / GNOME-style pill toggle switch.
    Supports keyboard navigation (Space/Enter) and smooth sliding knob.
    """
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(48, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self._checked = checked
        self._knob_position = 1.0 if self._checked else 0.0
        self._anim: Optional[QPropertyAnimation] = None

    @Property(float)
    def knob_position(self) -> float:
        return self._knob_position

    @knob_position.setter
    def knob_position(self, pos: float):
        self._knob_position = pos
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, animate: bool = True):
        if self._checked == checked and not self._anim:
            return
        self._checked = checked
        target = 1.0 if self._checked else 0.0

        if animate:
            if self._anim:
                self._anim.stop()
            self._anim = QPropertyAnimation(self, b"knob_position")
            self._anim.setDuration(200)
            self._anim.setStartValue(self._knob_position)
            self._anim.setEndValue(target)
            self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim.start()
        else:
            self._knob_position = target
            self.update()

    def toggle(self):
        self.setChecked(not self._checked)
        self.toggled.emit(self._checked)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
            event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        c = get_colors()
        accent_hex = c.get("ACCENT_PURPLE", "#3b82f6")
        is_dark = c.get("IS_DARK", True)

        active_color = QColor(accent_hex)
        inactive_color = QColor("#374151" if is_dark else "#d1d5db")

        # Interpolate track background color
        r = int(inactive_color.red() + (active_color.red() - inactive_color.red()) * self._knob_position)
        g = int(inactive_color.green() + (active_color.green() - inactive_color.green()) * self._knob_position)
        b = int(inactive_color.blue() + (active_color.blue() - inactive_color.blue()) * self._knob_position)
        track_color = QColor(r, g, b)

        h = self.height()
        w = self.width()
        radius = h / 2.0

        # Draw track
        painter.setBrush(track_color)
        if self.hasFocus():
            pen = QPen(QColor(accent_hex), 2)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), radius, radius)

        # Draw white knob
        knob_radius = (h - 6) / 2.0
        start_x = 3.0 + knob_radius
        end_x = w - 3.0 - knob_radius
        curr_x = start_x + (end_x - start_x) * self._knob_position

        # Subtle knob shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 40))
        painter.drawEllipse(QPointF(curr_x, h / 2.0 + 1), knob_radius, knob_radius)

        # Knob body
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(curr_x, h / 2.0), knob_radius, knob_radius)
        painter.end()


class ModernStepperControl(QWidget):
    """
    A modern [ - ] [ Value ] [ + ] [ ↺ ] stepper control widget.
    """
    valueChanged = Signal(int)

    def __init__(self, value: int = 15, min_val: int = 1, max_val: int = 180,
                 step: int = 5, suffix: str = " min", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._value = value
        self._min_val = min_val
        self._max_val = max_val
        self._default_val = value
        self._step = step
        self._suffix = suffix

        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        c = get_colors()
        is_dark = c.get("IS_DARK", True)
        btn_bg = "#262b36" if is_dark else "#e5e7eb"
        btn_hover = "#374151" if is_dark else "#d1d5db"
        text_col = c.get("TEXT_PRIMARY", "#f3f4f6")
        accent_col = c.get("ACCENT_PURPLE", "#3b82f6")

        btn_style = f"""
            QPushButton {{
                background-color: {btn_bg};
                color: {text_col};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
                border-color: {accent_col};
            }}
            QPushButton:pressed {{
                background-color: {accent_col};
                color: #ffffff;
            }}
            QPushButton:disabled {{
                opacity: 0.4;
            }}
        """

        self.btn_minus = QPushButton("−", self)
        self.btn_minus.setStyleSheet(btn_style)
        self.btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_minus.clicked.connect(self._decrement)

        self.lbl_value = QLabel(f"{self._value}{self._suffix}", self)
        self.lbl_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_value.setStyleSheet(f"""
            QLabel {{
                color: {text_col};
                font-weight: 600;
                font-size: 13px;
                padding: 0 6px;
                min-width: 54px;
            }}
        """)

        self.btn_plus = QPushButton("+", self)
        self.btn_plus.setStyleSheet(btn_style)
        self.btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_plus.clicked.connect(self._increment)

        self.btn_reset = QPushButton("↺", self)
        self.btn_reset.setStyleSheet(btn_style)
        self.btn_reset.setToolTip("Reset to default")
        self.btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset.clicked.connect(self._reset)

        layout.addWidget(self.btn_minus)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.btn_plus)
        layout.addWidget(self.btn_reset)

    def _increment(self):
        new_val = min(self._max_val, self._value + self._step)
        if new_val != self._value:
            self._value = new_val
            self._update_display()

    def _decrement(self):
        new_val = max(self._min_val, self._value - self._step)
        if new_val != self._value:
            self._value = new_val
            self._update_display()

    def _reset(self):
        if self._value != self._default_val:
            self._value = self._default_val
            self._update_display()

    def _update_display(self):
        self.lbl_value.setText(f"{self._value}{self._suffix}")
        self.valueChanged.emit(self._value)

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        clamped = max(self._min_val, min(self._max_val, val))
        if clamped != self._value:
            self._value = clamped
            self._update_display()


class SegmentedChipGroup(QWidget):
    """
    A segmented row of preset duration chips: [ 5m ] [ 15m ] [ 30m ] [ 1h ]
    """
    chipSelected = Signal(int)  # Emits selected minutes

    def __init__(self, presets: Optional[list[tuple[str, int]]] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.presets = presets or [("5m", 5), ("15m", 15), ("30m", 30), ("1h", 60)]
        self._buttons: list[QPushButton] = []
        self._selected_index = -1
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        c = get_colors()
        is_dark = c.get("IS_DARK", True)
        bg_chip = "#262b36" if is_dark else "#f3f4f6"
        hover_chip = "#374151" if is_dark else "#e5e7eb"
        text_col = c.get("TEXT_PRIMARY", "#f3f4f6")
        accent_col = c.get("ACCENT_PURPLE", "#3b82f6")

        for idx, (label, minutes) in enumerate(self.presets):
            btn = QPushButton(label, self)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_chip};
                    color: {text_col};
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 12px;
                    font-weight: 500;
                    min-height: 24px;
                }}
                QPushButton:hover {{
                    background-color: {hover_chip};
                    border-color: {accent_col};
                }}
                QPushButton:checked {{
                    background-color: {accent_col};
                    color: #ffffff;
                    font-weight: bold;
                    border: none;
                }}
            """)
            btn.clicked.connect(lambda _, m=minutes, i=idx: self._on_chip_clicked(m, i))
            self._buttons.append(btn)
            layout.addWidget(btn)

    def _on_chip_clicked(self, minutes: int, index: int):
        self._selected_index = index
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
        self.chipSelected.emit(minutes)

    def clearSelection(self):
        self._selected_index = -1
        for btn in self._buttons:
            btn.setChecked(False)


class AppRowWidget(QFrame):
    """
    An interactive card row for a protected app showing:
    - App icon + lock state badge
    - App name + status subtitle
    - Action button (Unlock / Relock / Open) with monochrome icons
    """
    authRequested = Signal(str)  # Emits desktop_name
    relockRequested = Signal(str)  # Emits app_id
    openRequested = Signal(dict)  # Emits app_dict

    def __init__(self, app_data: dict, is_authed: bool, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_data = app_data
        self.is_authed = is_authed

        self._build_ui()

    def _build_ui(self):
        self.setObjectName("appRow")
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        c = get_colors()
        is_dark = c.get("IS_DARK", True)
        text_primary = c.get("TEXT_PRIMARY", "#f3f4f6")
        text_secondary = c.get("TEXT_SECONDARY", "#9ca3af")
        accent_col = c.get("ACCENT_PURPLE", "#3b82f6")
        success_col = c.get("SUCCESS_GREEN", "#10b981")
        danger_col = c.get("DANGER_RED", "#ef4444")

        app_name = self.app_data.get("name") or self.app_data.get("id", "App")
        icon_name = self.app_data.get("icon", "")

        # Icon with badge
        base_icon = resolve_app_icon(icon_name)
        composited = composite_tray_icon(base_icon, is_locked=not self.is_authed)
        self.icon_lbl = QLabel(self)
        self.icon_lbl.setPixmap(composited.pixmap(26, 26))
        self.icon_lbl.setFixedSize(26, 26)
        layout.addWidget(self.icon_lbl)

        # Name and status labels in vertical box
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(1)

        self.name_lbl = QLabel(app_name, self)
        self.name_lbl.setStyleSheet(f"""
            QLabel {{
                color: {text_primary};
                font-weight: 600;
                font-size: 13px;
            }}
        """)
        
        status_text = "Unlocked" if self.is_authed else "Locked"
        status_color = success_col if self.is_authed else text_secondary
        self.status_lbl = QLabel(status_text, self)
        self.status_lbl.setStyleSheet(f"""
            QLabel {{
                color: {status_color};
                font-size: 11px;
            }}
        """)

        info_layout.addWidget(self.name_lbl)
        info_layout.addWidget(self.status_lbl)
        layout.addLayout(info_layout, stretch=1)

        # Action button
        self.action_btn = QPushButton(self)
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setFixedHeight(28)

        if not self.is_authed:
            self.action_btn.setText("Unlock")
            self.action_btn.setIcon(create_monochrome_icon("unlock", "#ffffff", 14))
            self.action_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {accent_col};
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {c.get("ACCENT_PURPLE_HOVER", "#2563eb")};
                }}
            """)
            d_name = self.app_data.get("desktop_name") or self.app_data.get("id", "")
            self.action_btn.clicked.connect(lambda: self.authRequested.emit(d_name))
        else:
            self.action_btn.setText("Relock")
            self.action_btn.setIcon(create_monochrome_icon("lock", danger_col, 14))
            self.action_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(239, 68, 68, 0.15);
                    color: {danger_col};
                    border: 1px solid rgba(239, 68, 68, 0.3);
                    border-radius: 6px;
                    padding: 4px 10px;
                    font-size: 12px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {danger_col};
                    color: #ffffff;
                }}
            """)
            app_id = self.app_data.get("id", "")
            self.action_btn.clicked.connect(lambda: self.relockRequested.emit(app_id))

        layout.addWidget(self.action_btn)

        # Card container styling
        bg_row = "rgba(255, 255, 255, 0.03)" if is_dark else "rgba(0, 0, 0, 0.02)"
        self.setStyleSheet(f"""
            QFrame#appRow {{
                background-color: {bg_row};
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
            }}
            QFrame#appRow:hover {{
                background-color: rgba(255, 255, 255, 0.07);
                border-color: rgba(255, 255, 255, 0.15);
            }}
        """)


class ActionNavRow(QFrame):
    """
    A clickable action row with monochrome vector icon, title, optional subtitle, and right chevron.
    """
    clicked = Signal()

    def __init__(self, icon_name: str, title: str, subtitle: str = "",
                 danger: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.danger = danger
        self.icon_name = icon_name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        c = get_colors()
        is_dark = c.get("IS_DARK", True)
        text_primary = c.get("TEXT_PRIMARY", "#f3f4f6")
        text_secondary = c.get("TEXT_SECONDARY", "#9ca3af")
        danger_col = c.get("DANGER_RED", "#ef4444")
        icon_col = danger_col if danger else text_secondary

        # Monochrome Icon
        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(20, 20)
        pix = create_monochrome_pixmap(icon_name, color_hex=icon_col, size=20)
        self.icon_lbl.setPixmap(pix)
        layout.addWidget(self.icon_lbl)

        # Title / Subtitle
        vbox = QVBoxLayout()
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(1)

        title_col = danger_col if danger else text_primary
        self.title_lbl = QLabel(title, self)
        self.title_lbl.setStyleSheet(f"""
            QLabel {{
                color: {title_col};
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        vbox.addWidget(self.title_lbl)

        if subtitle:
            self.sub_lbl = QLabel(subtitle, self)
            self.sub_lbl.setStyleSheet(f"color: {text_secondary}; font-size: 11px;")
            vbox.addWidget(self.sub_lbl)

        layout.addLayout(vbox, stretch=1)

        # Trailing Chevron
        if not danger:
            self.chevron_lbl = QLabel(self)
            self.chevron_lbl.setFixedSize(14, 14)
            self.chevron_lbl.setPixmap(create_monochrome_pixmap("chevron", color_hex=text_secondary, size=14))
            layout.addWidget(self.chevron_lbl)

        self.setObjectName("navRow")
        self._apply_style()

    def _apply_style(self):
        c = get_colors()
        is_dark = c.get("IS_DARK", True)
        hover_bg = "rgba(239, 68, 68, 0.12)" if self.danger else ("rgba(255, 255, 255, 0.07)" if is_dark else "rgba(0, 0, 0, 0.05)")

        self.setStyleSheet(f"""
            QFrame#navRow {{
                background-color: transparent;
                border-radius: 8px;
            }}
            QFrame#navRow:hover {{
                background-color: {hover_bg};
            }}
        """)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clicked.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class FaceGateTrayPopup(QFrame):
    """
    Modern Quick Settings Popup & Control Center for FaceGATE.
    Anchored cleanly next to the system tray icon with minimalist monochrome line icons.
    """
    closed = Signal()

    def __init__(self, main_app, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.main_app = main_app
        self.setWindowFlags(
            Qt.WindowType.Popup |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFixedWidth(360)

        # Refresh countdown timer
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self._on_tick)

        self._build_ui()

    def _build_ui(self):
        c = get_colors()
        is_dark = c.get("IS_DARK", True)
        bg_card = "#16171d" if is_dark else "#ffffff"
        border_col = "rgba(255, 255, 255, 0.12)" if is_dark else "rgba(0, 0, 0, 0.12)"
        text_primary = c.get("TEXT_PRIMARY", "#f3f4f6")
        text_secondary = c.get("TEXT_SECONDARY", "#9ca3af")
        accent_col = c.get("ACCENT_PURPLE", "#3b82f6")

        self.setObjectName("popupContainer")
        self.setStyleSheet(f"""
            QFrame#popupContainer {{
                background-color: {bg_card};
                border: 1px solid {border_col};
                border-radius: 16px;
            }}
        """)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # -------------------------------------------------------------
        # 1. Header Card: Master Status & Toggle Switch
        # -------------------------------------------------------------
        header_card = QFrame(self)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        self.master_icon = QLabel(header_card)
        self.master_icon.setFixedSize(26, 26)
        self.master_icon.setPixmap(create_monochrome_pixmap("shield", text_primary, 24))
        header_layout.addWidget(self.master_icon)

        title_vbox = QVBoxLayout()
        title_vbox.setContentsMargins(0, 0, 0, 0)
        title_vbox.setSpacing(2)

        self.lbl_title = QLabel("FaceGate Guard", header_card)
        self.lbl_title.setStyleSheet(f"""
            QLabel {{
                color: {text_primary};
                font-size: 15px;
                font-weight: bold;
            }}
        """)

        self.lbl_subtitle = QLabel("Guarding protected apps", header_card)
        self.lbl_subtitle.setStyleSheet(f"""
            QLabel {{
                color: {text_secondary};
                font-size: 12px;
            }}
        """)

        title_vbox.addWidget(self.lbl_title)
        title_vbox.addWidget(self.lbl_subtitle)
        header_layout.addLayout(title_vbox, stretch=1)

        self.master_switch = ModernToggleSwitch(checked=True, parent=header_card)
        self.master_switch.toggled.connect(self._handle_master_toggle)
        header_layout.addWidget(self.master_switch)

        main_layout.addWidget(header_card)

        # -------------------------------------------------------------
        # 2. Quick Actions Bar: [ Relock All ] [ Quick Scan ]
        # -------------------------------------------------------------
        actions_bar = QHBoxLayout()
        actions_bar.setSpacing(8)

        btn_action_style = f"""
            QPushButton {{
                background-color: rgba(255, 255, 255, 0.05);
                color: {text_primary};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
                min-height: 28px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.12);
                border-color: {accent_col};
            }}
            QPushButton:pressed {{
                background-color: {accent_col};
                color: #ffffff;
            }}
            QPushButton:disabled {{
                opacity: 0.35;
                color: {text_secondary};
            }}
        """

        self.btn_relock_all = QPushButton("Relock All", self)
        self.btn_relock_all.setIcon(create_monochrome_icon("lock", text_primary, 15))
        self.btn_relock_all.setStyleSheet(btn_action_style)
        self.btn_relock_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_relock_all.clicked.connect(self._handle_relock_all)
        actions_bar.addWidget(self.btn_relock_all)

        self.btn_quick_scan = QPushButton("Quick Scan", self)
        self.btn_quick_scan.setIcon(create_monochrome_icon("scan", text_primary, 15))
        self.btn_quick_scan.setStyleSheet(btn_action_style)
        self.btn_quick_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quick_scan.clicked.connect(self._handle_quick_scan)
        actions_bar.addWidget(self.btn_quick_scan)

        main_layout.addLayout(actions_bar)
        main_layout.addWidget(self._create_divider())

        # -------------------------------------------------------------
        # 3. Pause Stepper & Presets Row
        # -------------------------------------------------------------
        pause_section = QVBoxLayout()
        pause_section.setSpacing(6)

        pause_header = QHBoxLayout()
        lbl_pause = QLabel("Pause Protection", self)
        lbl_pause.setStyleSheet(f"color: {text_secondary}; font-size: 11px; font-weight: 700; text-transform: uppercase;")
        pause_header.addWidget(lbl_pause)
        pause_header.addStretch()

        self.btn_pause_action = QPushButton("Pause", self)
        self.btn_pause_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause_action.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent_col};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {c.get("ACCENT_PURPLE_HOVER", "#2563eb")};
            }}
        """)
        self.btn_pause_action.clicked.connect(self._handle_pause_click)
        pause_header.addWidget(self.btn_pause_action)
        pause_section.addLayout(pause_header)

        # Stepper & Preset chips row
        stepper_chips_row = QHBoxLayout()
        stepper_chips_row.setSpacing(8)

        self.pause_stepper = ModernStepperControl(value=15, min_val=1, max_val=120, step=5, suffix="m", parent=self)
        stepper_chips_row.addWidget(self.pause_stepper)

        self.preset_chips = SegmentedChipGroup(presets=[("5m", 5), ("15m", 15), ("30m", 30), ("1h", 60)], parent=self)
        self.preset_chips.chipSelected.connect(lambda mins: (self.pause_stepper.setValue(mins), self.main_app.disable_for(mins), self.refresh_state()))
        stepper_chips_row.addWidget(self.preset_chips)

        pause_section.addLayout(stepper_chips_row)
        main_layout.addLayout(pause_section)
        main_layout.addWidget(self._create_divider())

        # -------------------------------------------------------------
        # 4. Protected Apps Section
        # -------------------------------------------------------------
        apps_section_hdr = QHBoxLayout()
        lbl_apps = QLabel("Protected Applications", self)
        lbl_apps.setStyleSheet(f"color: {text_secondary}; font-size: 11px; font-weight: 700; text-transform: uppercase;")
        apps_section_hdr.addWidget(lbl_apps)
        
        self.lbl_app_count = QLabel("0 active", self)
        self.lbl_app_count.setStyleSheet(f"color: {text_secondary}; font-size: 11px;")
        apps_section_hdr.addStretch()
        apps_section_hdr.addWidget(self.lbl_app_count)
        main_layout.addLayout(apps_section_hdr)

        self.apps_container = QVBoxLayout()
        self.apps_container.setSpacing(6)
        main_layout.addLayout(self.apps_container)

        main_layout.addWidget(self._create_divider())

        # -------------------------------------------------------------
        # 5. Navigation & Preferences (Clean monochrome line icons)
        # -------------------------------------------------------------
        nav_vbox = QVBoxLayout()
        nav_vbox.setSpacing(2)

        self.row_settings = ActionNavRow("gear", "Settings...", "Preferences & security configuration", parent=self)
        self.row_settings.clicked.connect(self._handle_open_settings)
        nav_vbox.addWidget(self.row_settings)

        self.row_enroll = ActionNavRow("user", "Enroll Face...", "Train or update face profiles", parent=self)
        self.row_enroll.clicked.connect(self._handle_open_enrollment)
        nav_vbox.addWidget(self.row_enroll)

        main_layout.addLayout(nav_vbox)
        main_layout.addWidget(self._create_divider())

        # -------------------------------------------------------------
        # 6. Quit Row
        # -------------------------------------------------------------
        self.row_quit = ActionNavRow("power", "Quit FaceGate", "", danger=True, parent=self)
        self.row_quit.clicked.connect(self._handle_quit)
        main_layout.addWidget(self.row_quit)

    def _create_divider(self) -> QFrame:
        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); max-height: 1px; border: none;")
        return divider

    def refresh_state(self):
        """Re-reads application state and updates all UI components."""
        is_active = self.main_app.is_active()
        self.master_switch.setChecked(is_active, animate=False)

        c = get_colors()
        text_primary = c.get("TEXT_PRIMARY", "#f3f4f6")
        text_secondary = c.get("TEXT_SECONDARY", "#9ca3af")
        warning_col = c.get("WARNING_AMBER", "#f59e0b")

        # Update status header
        if is_active:
            self.lbl_title.setText("FaceGate Guard")
            self.lbl_subtitle.setText("Active • Guarding protected apps")
            self.master_icon.setPixmap(create_monochrome_pixmap("shield", text_primary, 24))
            self.btn_pause_action.setText("Pause")
        else:
            if self.main_app.disabled_until:
                remaining = int(self.main_app.get_remaining_disabled_seconds())
                if remaining > 0:
                    mins, secs = divmod(remaining, 60)
                    self.lbl_title.setText("FaceGate Paused")
                    self.lbl_subtitle.setText(f"Resuming in {mins:02d}:{secs:02d}")
                    self.master_icon.setPixmap(create_monochrome_pixmap("pause", warning_col, 24))
                    self.btn_pause_action.setText("Resume Now")
                else:
                    self.lbl_title.setText("FaceGate Inactive")
                    self.lbl_subtitle.setText("Protection disabled")
                    self.master_icon.setPixmap(create_monochrome_pixmap("shield", text_secondary, 24))
                    self.btn_pause_action.setText("Resume")
            else:
                self.lbl_title.setText("FaceGate Inactive")
                self.lbl_subtitle.setText("Protection disabled")
                self.master_icon.setPixmap(create_monochrome_pixmap("shield", text_secondary, 24))
                self.btn_pause_action.setText("Resume")

        # Update relock all button state
        protected_apps = self.main_app.get_protected_apps()
        has_unlocked = any(self.main_app.is_app_authorized(app["id"]) for app in protected_apps if isinstance(app, dict))
        self.btn_relock_all.setEnabled(is_active and has_unlocked)

        # Rebuild protected apps list
        while self.apps_container.count() > 0:
            item = self.apps_container.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        tray_apps = [app for app in protected_apps if (app.get("show_in_tray", True) if isinstance(app, dict) else True)][:5]
        self.lbl_app_count.setText(f"{len(tray_apps)} displayed")

        if not tray_apps:
            empty_lbl = QLabel("No apps configured for tray display", self)
            empty_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 12px; font-style: italic; padding: 6px 0;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.apps_container.addWidget(empty_lbl)
        else:
            for app in tray_apps:
                app_dict = app if isinstance(app, dict) else {"id": app, "name": app, "desktop_name": app}
                app_id = app_dict.get("id", "")
                is_authed = self.main_app.is_app_authorized(app_id)
                row = AppRowWidget(app_dict, is_authed, parent=self)
                row.authRequested.connect(self._handle_app_auth)
                row.relockRequested.connect(self._handle_app_relock)
                row.openRequested.connect(self._handle_app_open)
                self.apps_container.addWidget(row)

        self.adjustSize()

    def _on_tick(self):
        """Called every second when visible to update live pause timers."""
        if self.isVisible() and not self.main_app.is_active() and self.main_app.disabled_until:
            remaining = int(self.main_app.get_remaining_disabled_seconds())
            if remaining > 0:
                mins, secs = divmod(remaining, 60)
                self.lbl_subtitle.setText(f"Resuming in {mins:02d}:{secs:02d}")
            else:
                self.refresh_state()

    def show_at_tray(self, tray_geo: QRect, cursor_pos: Optional[QPoint] = None):
        """
        Positions and displays the popup anchored above/below the system tray icon,
        or near the cursor position. Clamps within the current screen boundaries.
        """
        self.refresh_state()
        self.refresh_timer.start(1000)

        # Get screen geometry
        app = QApplication.instance()
        screen = None
        if tray_geo.isValid():
            screen = QApplication.screenAt(tray_geo.center())
        if not screen and cursor_pos:
            screen = QApplication.screenAt(cursor_pos)
        if not screen and isinstance(app, QApplication):
            screen = app.primaryScreen()

        if screen:
            screen_geo = screen.availableGeometry()
        else:
            screen_geo = QRect(0, 0, 1920, 1080)

        popup_w = self.width()
        popup_h = self.height()
        margin = 8

        # Calculate position based on tray geometry or cursor
        if tray_geo.isValid():
            ref_pos = tray_geo.center()
        elif cursor_pos:
            ref_pos = cursor_pos
        else:
            ref_pos = screen_geo.topRight()

        # Horizontal alignment: center on tray icon
        x = ref_pos.x() - popup_w // 2

        # Clamp horizontal
        if x + popup_w > screen_geo.right() - margin:
            x = screen_geo.right() - popup_w - margin
        if x < screen_geo.left() + margin:
            x = screen_geo.left() + margin

        # Vertical alignment: determine if tray is at top or bottom
        if tray_geo.isValid():
            if tray_geo.top() < screen_geo.center().y():
                # Top panel: place below tray icon
                y = tray_geo.bottom() + margin
            else:
                # Bottom panel: place above tray icon
                y = tray_geo.top() - popup_h - margin
        else:
            if ref_pos.y() < screen_geo.center().y():
                y = ref_pos.y() + margin
            else:
                y = ref_pos.y() - popup_h - margin

        # Clamp vertical
        if y + popup_h > screen_geo.bottom() - margin:
            y = screen_geo.bottom() - popup_h - margin
        if y < screen_geo.top() + margin:
            y = screen_geo.top() + margin

        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def hideEvent(self, event):
        self.refresh_timer.stop()
        self.closed.emit()
        super().hideEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
        else:
            super().keyPressEvent(event)

    # -------------------------------------------------------------
    # Action Handlers
    # -------------------------------------------------------------
    def _handle_master_toggle(self, checked: bool):
        if checked:
            self.main_app.resume()
        else:
            mins = self.pause_stepper.value()
            self.main_app.disable_for(mins)
        self.refresh_state()

    def _handle_pause_click(self):
        if self.main_app.is_active():
            mins = self.pause_stepper.value()
            self.main_app.disable_for(mins)
        else:
            self.main_app.resume()
        self.refresh_state()

    def _handle_relock_all(self):
        self.main_app.relock_all()
        self.refresh_state()

    def _handle_quick_scan(self):
        self.hide()
        self.main_app.trigger_manual_auth("quick_scan")

    def _handle_app_auth(self, desktop_name: str):
        self.hide()
        self.main_app.trigger_manual_auth(desktop_name)

    def _handle_app_relock(self, app_id: str):
        self.main_app.relock_app(app_id)
        self.refresh_state()

    def _handle_app_open(self, app_dict: dict):
        self.hide()
        app_id = app_dict.get("id")
        resumed = 0
        if hasattr(self.main_app, 'session_manager'):
            resumed = self.main_app.session_manager.resume_suspended_processes(app_id)
        if resumed == 0:
            from ui.tray import launch_app_command
            launch_app_command(app_dict)

    def _handle_open_settings(self):
        self.hide()
        self.main_app.open_settings()

    def _handle_open_enrollment(self):
        self.hide()
        self.main_app.open_enrollment()

    def _handle_quit(self):
        self.hide()
        self.main_app.quit_app()
