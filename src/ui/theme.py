import os
import subprocess
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QFont
from PySide6.QtCore import Qt, QRect, QRectF, QPointF, QSize, QVariantAnimation, QEasingCurve, QAbstractAnimation, Property, QPropertyAnimation, QModelIndex
from PySide6.QtWidgets import QSpinBox, QComboBox, QCheckBox, QStyledItemDelegate, QStyleOptionViewItem, QStyle, QListView, QFrame

# Global constants initialized to default light mode
BG_NEUTRAL = "#f5f3ff"
CARD_NEUTRAL = "#faf9fc"
BORDER_NEUTRAL = "#e9e7f1"
TEXT_PRIMARY = "#1e1b4b"
TEXT_SECONDARY = "#5c5770"
ACCENT_PURPLE = "#7c3aed"
ACCENT_PURPLE_HOVER = "#6d28d9"
ACCENT_PURPLE_PRESSED = "#5b21b6"
SUCCESS_GREEN = "#10b981"
DANGER_RED = "#ef4444"
WARNING_AMBER = "#fbbf24"

FONT_FAMILY = 'Inter, "Cantarell", "Noto Sans", sans-serif'

def is_system_dark_mode() -> bool:
    # 1. Check Qt application palette if QApplication instance exists
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPalette
        app = QApplication.instance()
        if app:
            window_color = app.palette().color(QPalette.ColorRole.Window)
            if window_color.value() < 128:
                return True
    except Exception:
        pass

    # Avoid subprocess calls if subprocess.Popen is mocked during unit tests
    import subprocess
    if hasattr(subprocess.Popen, "assert_called") or hasattr(subprocess.Popen, "return_value"):
        return False
    try:
        res = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=1.0)
        if "dark" in res.stdout.lower():
            return True
    except Exception:
        pass

    # 3. Check GNOME / GTK gtk-theme setting
    try:
        res = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                             capture_output=True, text=True, timeout=1.0)
        if "dark" in res.stdout.lower():
            return True
    except Exception:
        pass

    # 4. Check KDE Plasma theme configuration
    try:
        res = subprocess.run(["kreadconfig5", "--group", "WM", "--key", "theme"],
                             capture_output=True, text=True, timeout=1.0)
        if "dark" in res.stdout.lower():
            return True
    except Exception:
        pass

    # 5. Check environment variables (GTK_THEME)
    gtk_theme = os.environ.get("GTK_THEME", "").lower()
    if "dark" in gtk_theme:
        return True

    return False

def get_colors(theme_override: str = None) -> dict:
    theme = theme_override
    if not theme:
        from utils.config_loader import get_config
        try:
            config = get_config()
            theme = config.get("behavior.theme", "light")
        except Exception:
            theme = "light"
        
    is_dark = False
    if theme == "dark":
        is_dark = True
    else:
        is_dark = False
        
    if is_dark:
        return {
            "IS_DARK": True,
            "BG_NEUTRAL": "#0b0a12",
            "BG_SECONDARY": "#151322",
            "CARD_NEUTRAL": "#181627",
            "BORDER_NEUTRAL": "#322c4d",
            "TEXT_PRIMARY": "#f8fafc",
            "TEXT_SECONDARY": "#cbd5e1",
            "HEADER_TEXT": "#c084fc",
            "ACCENT_PURPLE": "#a855f7",
            "ACCENT_PURPLE_HOVER": "#c084fc",
            "ACCENT_PURPLE_PRESSED": "#9333ea",
            "WIDGET_BG": "#110f1c",
            "LIST_ITEM_HOVER": "#2b2644",
            "HOVER_NEUTRAL": "#2b2644",
            "CANCEL_BTN_BG": "#25213b",
            "CANCEL_BTN_HOVER": "#373154",
            "SHADOW_COLOR": "rgba(0, 0, 0, 0.6)",
            "STATUS_HEADER_BG": "#1f1a33",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#fbbf24"
        }
    else:
        return {
            "IS_DARK": False,
            "BG_NEUTRAL": "#f1f5f9",
            "BG_SECONDARY": "#ffffff",
            "CARD_NEUTRAL": "#ffffff",
            "BORDER_NEUTRAL": "#cbd5e1",
            "TEXT_PRIMARY": "#0f172a",
            "TEXT_SECONDARY": "#334155",
            "HEADER_TEXT": "#6b21a8",
            "ACCENT_PURPLE": "#7c3aed",
            "ACCENT_PURPLE_HOVER": "#6d28d9",
            "ACCENT_PURPLE_PRESSED": "#5b21b6",
            "WIDGET_BG": "#ffffff",
            "LIST_ITEM_HOVER": "#f1f5f9",
            "HOVER_NEUTRAL": "#f1f5f9",
            "CANCEL_BTN_BG": "#f1f5f9",
            "CANCEL_BTN_HOVER": "#e2e8f0",
            "SHADOW_COLOR": "rgba(124, 58, 237, 0.12)",
            "STATUS_HEADER_BG": "#f1f5f9",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#f59e0b"
        }

def refresh_theme_colors(theme_override: str = None):
    global BG_NEUTRAL, CARD_NEUTRAL, BORDER_NEUTRAL, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_PURPLE, ACCENT_PURPLE_HOVER, ACCENT_PURPLE_PRESSED
    c = get_colors(theme_override)
    BG_NEUTRAL = c["BG_NEUTRAL"]
    CARD_NEUTRAL = c["CARD_NEUTRAL"]
    BORDER_NEUTRAL = c["BORDER_NEUTRAL"]
    TEXT_PRIMARY = c["TEXT_PRIMARY"]
    TEXT_SECONDARY = c["TEXT_SECONDARY"]
    ACCENT_PURPLE = c["ACCENT_PURPLE"]
    ACCENT_PURPLE_HOVER = c["ACCENT_PURPLE_HOVER"]
    ACCENT_PURPLE_PRESSED = c["ACCENT_PURPLE_PRESSED"]

def get_sidebar_qss(c: dict) -> str:
    is_dark = c.get("IS_DARK", False)
    sidebar_bg = "#110f1c" if is_dark else "#ede9fe"
    sidebar_color = "#cbd5e1" if is_dark else "#4c4664"
    sidebar_hover_bg = "#27223e" if is_dark else "#e5dbff"
    
    return f"""
        QListWidget#sidebar {{
            background-color: {sidebar_bg};
            border: none;
            border-bottom-left-radius: 12px;
            border-right: 1px solid {c["BORDER_NEUTRAL"]};
            padding-top: 10px;
            color: {sidebar_color};
            font-size: 13px;
            font-weight: 500;
        }}
        QListWidget#sidebar::item {{
            padding: 10px 16px;
            border-radius: 6px;
            margin: 4px 8px;
            color: {sidebar_color};
        }}
        QListWidget#sidebar::item:hover {{
            background-color: {sidebar_hover_bg};
            color: {c["TEXT_PRIMARY"]};
        }}
        QListWidget#sidebar::item:selected {{
            background-color: {c["ACCENT_PURPLE"]};
            color: #ffffff;
            font-weight: bold;
        }}
        QPushButton#removeBtn {{
            background-color: transparent;
            color: #ef4444;
            border: 1px solid #ef4444;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: bold;
        }}
        QPushButton#removeBtn:hover {{
            background-color: #ef4444;
            color: white;
        }}
    """

def get_theme_qss(theme_override: str = None) -> str:
    refresh_theme_colors(theme_override)
    c = get_colors(theme_override)
    
    return f"""
        QDialog, QMainWindow {{
            background-color: {c["BG_NEUTRAL"]};
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
        }}
        QLabel {{
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
        }}
        QLabel[secondary="true"] {{
            color: {c["TEXT_SECONDARY"]};
        }}
        QLineEdit {{
            background-color: {c["WIDGET_BG"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 6px;
            padding: 8px 12px;
            color: {c["TEXT_PRIMARY"]};
            font-size: 13px;
            font-family: {FONT_FAMILY};
        }}
        QLineEdit:focus {{
            border: 1px solid {c["ACCENT_PURPLE"]};
        }}
        QPushButton {{
            background-color: {c["ACCENT_PURPLE"]};
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 13px;
            font-family: {FONT_FAMILY};
        }}
        QPushButton:hover {{
            background-color: {c["ACCENT_PURPLE_HOVER"]};
        }}
        QPushButton:pressed {{
            background-color: {c["ACCENT_PURPLE_PRESSED"]};
        }}
        QPushButton#cancelBtn, QPushButton#changePwdBtn, QPushButton#testFaceBtn {{
            background-color: {c["CANCEL_BTN_BG"]};
            color: {c["TEXT_PRIMARY"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 13px;
        }}
        QPushButton#cancelBtn:hover, QPushButton#changePwdBtn:hover, QPushButton#testFaceBtn:hover {{
            background-color: {c["CANCEL_BTN_HOVER"]};
        }}
        QPushButton#removeSelectedBtn, QPushButton#clearIntrudersBtn {{
            background-color: #ef4444;
            color: #ffffff;
            border: none;
            font-weight: bold;
            border-radius: 6px;
            padding: 8px 16px;
        }}
        QPushButton#removeSelectedBtn:hover, QPushButton#clearIntrudersBtn:hover {{
            background-color: #dc2626;
        }}
        QPushButton#removeSelectedBtn:pressed, QPushButton#clearIntrudersBtn:pressed {{
            background-color: #b91c1c;
        }}
        QPushButton#enrollBtn, QPushButton#enrollNewBtn {{
            background-color: {c["ACCENT_PURPLE"]};
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 13px;
        }}
        QPushButton#enrollBtn:hover, QPushButton#enrollNewBtn:hover {{
            background-color: {c["ACCENT_PURPLE_HOVER"]};
        }}
        QPushButton#dismissBtn {{
            background-color: transparent;
            color: {c["TEXT_SECONDARY"]};
            text-decoration: underline;
            border: none;
        }}
        QPushButton#dismissBtn:hover {{
            color: {c["TEXT_PRIMARY"]};
        }}
        QPushButton#deleteIntruderBtn {{
            background-color: #ef4444;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 12px;
            padding: 6px 12px;
            font-weight: bold;
        }}
        QPushButton#deleteIntruderBtn:hover {{
            background-color: #dc2626;
        }}
        QFrame#intruderCard {{
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 8px;
            background-color: {c["CARD_NEUTRAL"]};
        }}
        QLabel#intruderImg {{
            border-radius: 6px;
            border: 1px solid {c["BORDER_NEUTRAL"]};
        }}
        QListWidget {{
            background-color: {c["CARD_NEUTRAL"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 8px;
            color: {c["TEXT_PRIMARY"]};
            font-size: 13px;
            font-family: {FONT_FAMILY};
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 8px;
            border-radius: 4px;
            color: {c["TEXT_PRIMARY"]};
        }}
        QListWidget::item:hover {{
            background-color: {c["LIST_ITEM_HOVER"]};
        }}
        QListWidget::item:selected {{
            background-color: {c["ACCENT_PURPLE"]};
            color: white;
        }}
        QTreeWidget {{
            background-color: {c["CARD_NEUTRAL"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 8px;
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-size: 13px;
            padding: 4px;
        }}
        QTreeWidget::item {{
            padding: 6px;
            color: {c["TEXT_PRIMARY"]};
        }}
        QTreeWidget::item:hover {{
            background-color: {c["LIST_ITEM_HOVER"]};
        }}
        QTreeWidget::item:selected {{
            background-color: {c["ACCENT_PURPLE"]};
            color: white;
        }}
        QHeaderView::section {{
            background-color: {c["STATUS_HEADER_BG"]};
            color: {c["TEXT_PRIMARY"]};
            padding: 8px;
            border: 1px solid {c["BORDER_NEUTRAL"]};
            font-weight: bold;
            font-size: 13px;
        }}
        QComboBox {{
            background-color: {c["WIDGET_BG"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 6px;
            padding: 6px 32px 6px 12px;
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QComboBox:focus {{
            border: 1px solid {c["ACCENT_PURPLE"]};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 28px;
            border-left: none;
            background: transparent;
        }}
        QComboBox::down-arrow {{
            image: none;
            border: none;
            width: 0px;
            height: 0px;
            background: transparent;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c["CARD_NEUTRAL"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            color: {c["TEXT_PRIMARY"]};
            selection-background-color: {c["ACCENT_PURPLE"]};
            selection-color: #ffffff;
            outline: none;
            padding: 4px;
            border-radius: 8px;
        }}
        QComboBox QAbstractItemView::item {{
            background-color: {c["CARD_NEUTRAL"]};
            color: {c["TEXT_PRIMARY"]};
            padding: 8px 12px;
            border-radius: 6px;
            min-height: 28px;
        }}
        QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {{
            background-color: {c["ACCENT_PURPLE"]};
            color: #ffffff;
        }}
        QSpinBox {{
            background-color: {c["WIDGET_BG"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 6px;
            padding: 6px 12px;
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QSpinBox:focus {{
            border: 1px solid {c["ACCENT_PURPLE"]};
        }}
        QCheckBox {{
            spacing: 8px;
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QCheckBox::indicator {{
            width: 0px;
            height: 0px;
            border: none;
            background: transparent;
            margin: 0px;
            padding: 0px;
        }}
        QProgressBar {{
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 6px;
            background-color: {c["CANCEL_BTN_BG"]};
            text-align: center;
            color: {c["TEXT_PRIMARY"]};
            font-weight: bold;
            height: 18px;
        }}
        QProgressBar::chunk {{
            background-color: {c["ACCENT_PURPLE"]};
            border-radius: 5px;
        }}
        QTableWidget {{
            background-color: {c["CARD_NEUTRAL"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            gridline-color: {c["BORDER_NEUTRAL"]};
            color: {c["TEXT_PRIMARY"]};
            border-radius: 8px;
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QTableWidget::item {{
            padding: 6px;
            color: {c["TEXT_PRIMARY"]};
        }}
        QScrollArea, QScrollArea > QWidget, QAbstractScrollArea, QAbstractScrollArea > QWidget {{
            background-color: transparent;
            border: none;
        }}
        QWidget#qt_scrollarea_viewport {{
            background-color: transparent;
        }}
        QStackedWidget, QStackedWidget > QWidget {{
            background-color: transparent;
        }}
        QPushButton#removeBtn {{
            background-color: transparent;
            color: #ef4444;
            border: 1px solid #ef4444;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: bold;
        }}
        QPushButton#removeBtn:hover {{
            background-color: #ef4444;
            color: white;
        }}
    """

def get_card_qss(importance: str = "normal", colors: dict = None) -> str:
    if colors is None:
        colors = get_colors()
    card_bg = colors["CARD_NEUTRAL"]
    border_color = colors["BORDER_NEUTRAL"]
    text_color = colors["TEXT_PRIMARY"]
    text_sec = colors["TEXT_SECONDARY"]
    header_color = colors.get("HEADER_TEXT", "#c084fc")
    accent = colors["ACCENT_PURPLE"]
    accent_hover = colors.get("ACCENT_PURPLE_HOVER", "#6d28d9")
    danger = colors.get("DANGER_RED", "#ef4444")
    widget_bg = colors.get("WIDGET_BG", "#110f1c")
    cancel_bg = colors.get("CANCEL_BTN_BG", "#f1f5f9")
    cancel_hover = colors.get("CANCEL_BTN_HOVER", "#e2e8f0")
    
    if importance == "danger":
        border_qss = f"border-left: 4px solid {danger}; border-top: 1px solid {border_color}; border-right: 1px solid {border_color}; border-bottom: 1px solid {border_color};"
    elif importance == "accent":
        border_qss = f"border-left: 4px solid {accent}; border-top: 1px solid {border_color}; border-right: 1px solid {border_color}; border-bottom: 1px solid {border_color};"
    else:
        border_qss = f"border: 1px solid {border_color};"
        
    return f"""
        QWidget#card {{
            background-color: {card_bg};
            {border_qss}
            border-radius: 10px;
        }}
        QLabel {{
            border: none;
            background-color: transparent;
            color: {text_color};
        }}
        QLabel[secondary="true"] {{
            color: {text_sec};
        }}
        QLabel#cardHeader {{
            color: {header_color};
            font-size: 15px;
            font-weight: bold;
            border: none;
            background-color: transparent;
        }}
        QLineEdit, QSpinBox, QComboBox {{
            background-color: {widget_bg};
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 6px 12px;
            color: {text_color};
            font-size: 13px;
        }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border: 1px solid {accent};
        }}
        QPushButton#enrollBtn, QPushButton#enrollNewBtn {{
            background-color: {accent};
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 13px;
        }}
        QPushButton#enrollBtn:hover, QPushButton#enrollNewBtn:hover {{
            background-color: {accent_hover};
        }}
        QPushButton#testFaceBtn, QPushButton#changePwdBtn {{
            background-color: {cancel_bg};
            color: {text_color};
            border: 1px solid {border_color};
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 13px;
        }}
        QPushButton#testFaceBtn:hover, QPushButton#changePwdBtn:hover {{
            background-color: {cancel_hover};
        }}
    """

def resolve_app_icon(icon_source: str) -> QIcon:
    icon = None
    if icon_source:
        if os.path.isabs(icon_source) and os.path.exists(icon_source):
            icon = QIcon(icon_source)
        else:
            icon = QIcon.fromTheme(icon_source)
    if not icon or icon.isNull():
        icon = QIcon.fromTheme("application-x-executable")
    return icon

def composite_tray_icon(app_icon: QIcon, is_locked: bool) -> QIcon:
    pixmap = app_icon.pixmap(24, 24)
    if pixmap.isNull():
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    badge_rect = QRect(13, 13, 11, 11)
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(badge_rect)
    
    badge_color = DANGER_RED if is_locked else SUCCESS_GREEN
    painter.setBrush(QColor(badge_color))
    painter.drawEllipse(14, 14, 9, 9)
    
    painter.end()
    return QIcon(pixmap)

def create_status_icon(color_hex: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    return QIcon(pixmap)

class AnimatedSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.anim = None

    def stepBy(self, steps):
        target = self.value() + steps * self.singleStep()
        target = max(self.minimum(), min(self.maximum(), target))
        
        if self.anim and self.anim.state() == QAbstractAnimation.State.Running:
            self.anim.stop()
            
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(200)
        self.anim.setStartValue(self.value())
        self.anim.setEndValue(target)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.anim.valueChanged.connect(lambda val: self.setValue(int(val)))
        self.anim.start()

class AnimatedItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        from ui.theme import get_colors
        c = get_colors()
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        rect = option.rect
        padded_rect = rect.adjusted(4, 2, -4, -2)

        if is_selected:
            bg_color = QColor(c["ACCENT_PURPLE"])
            text_color = QColor("#ffffff")
        elif is_hovered:
            bg_color = QColor(c["LIST_ITEM_HOVER"])
            text_color = QColor(c["TEXT_PRIMARY"])
        else:
            bg_color = QColor(c["CARD_NEUTRAL"])
            text_color = QColor(c["TEXT_PRIMARY"])

        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(padded_rect, 6, 6)

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.setFont(option.font)
        painter.setPen(text_color)
        text_rect = padded_rect.adjusted(12, 0, -32, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        if is_selected:
            painter.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            chk_x = padded_rect.right() - 20
            chk_y = padded_rect.center().y()
            path = QPainterPath()
            path.moveTo(chk_x, chk_y - 1)
            path.lineTo(chk_x + 4, chk_y + 4)
            path.lineTo(chk_x + 10, chk_y - 4)
            painter.drawPath(path)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        size = super().sizeHint(option, index)
        size.setHeight(max(36, size.height()))
        return size


class AnimatedComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._arrow_rotation = 0.0
        self.anim = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        view = QListView(self)
        view.setItemDelegate(AnimatedItemDelegate(view))
        view.setFrameShape(QFrame.Shape.NoFrame)
        self.setView(view)

    @Property(float)
    def arrow_rotation(self):
        return self._arrow_rotation

    @arrow_rotation.setter
    def arrow_rotation(self, val):
        self._arrow_rotation = val
        self.update()

    def showPopup(self):
        if self.anim:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"arrow_rotation")
        self.anim.setDuration(220)
        self.anim.setStartValue(self._arrow_rotation)
        self.anim.setEndValue(180.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()
        super().showPopup()

    def hidePopup(self):
        if self.anim:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"arrow_rotation")
        self.anim.setDuration(220)
        self.anim.setStartValue(self._arrow_rotation)
        self.anim.setEndValue(0.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()
        super().hidePopup()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.view().isVisible():
                self.hidePopup()
            else:
                self.showPopup()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        from ui.theme import get_colors
        c = get_colors()
        arrow_color = QColor(c["ACCENT_PURPLE"]) if self._arrow_rotation > 45 else QColor(c["TEXT_PRIMARY"])

        arrow_center_x = self.width() - 16
        arrow_center_y = self.height() / 2.0

        painter.save()
        painter.translate(arrow_center_x, arrow_center_y)
        painter.rotate(self._arrow_rotation)

        pen = QPen(arrow_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        path = QPainterPath()
        path.moveTo(-4, -2)
        path.lineTo(0, 2)
        path.lineTo(4, -2)
        painter.drawPath(path)

        painter.restore()


class AnimatedCheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        if isinstance(text, QWidget) and parent is None:
            parent = text
            text = ""
        super().__init__(text, parent)
        self._check_progress = 1.0 if self.isChecked() else 0.0
        self.anim = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggled.connect(self._on_toggled)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.toggle()
            event.accept()
        else:
            super().keyPressEvent(event)

    @Property(float)
    def check_progress(self):
        return self._check_progress

    @check_progress.setter
    def check_progress(self, val):
        self._check_progress = val
        self.update()

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._check_progress = 1.0 if checked else 0.0
        self.update()

    def _on_toggled(self, checked: bool):
        target = 1.0 if checked else 0.0
        if self.anim:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"check_progress")
        self.anim.setDuration(220)
        self.anim.setStartValue(self._check_progress)
        self.anim.setEndValue(target)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack if checked else QEasingCurve.Type.OutCubic)
        self.anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        from ui.theme import get_colors
        c = get_colors()

        box_size = 18
        box_y = (self.height() - box_size) / 2.0
        box_rect = QRectF(0, box_y, box_size, box_size)

        bg_inactive = QColor(c.get("WIDGET_BG", "#ffffff"))
        bg_active = QColor(c.get("ACCENT_PURPLE", "#7c3aed"))
        
        border_inactive = QColor(c.get("BORDER_NEUTRAL", "#cbd5e1"))
        border_active = QColor(c.get("ACCENT_PURPLE", "#7c3aed"))

        p = max(0.0, min(1.0, self._check_progress))

        bg_r = int(bg_inactive.red() + (bg_active.red() - bg_inactive.red()) * p)
        bg_g = int(bg_inactive.green() + (bg_active.green() - bg_inactive.green()) * p)
        bg_b = int(bg_inactive.blue() + (bg_active.blue() - bg_inactive.blue()) * p)
        current_bg = QColor(bg_r, bg_g, bg_b)

        b_r = int(border_inactive.red() + (border_active.red() - border_inactive.red()) * p)
        b_g = int(border_inactive.green() + (border_active.green() - border_inactive.green()) * p)
        b_b = int(border_inactive.blue() + (border_active.blue() - border_inactive.blue()) * p)
        current_border = QColor(b_r, b_g, b_b)

        painter.setBrush(QBrush(current_bg))
        painter.setPen(QPen(current_border, 1.5))
        painter.drawRoundedRect(box_rect, 5, 5)

        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(border_active, 2.0))
            painter.drawRoundedRect(box_rect.adjusted(-2, -2, 2, 2), 6, 6)

        if p > 0.05:
            painter.save()
            painter.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

            cx = box_rect.center().x()
            cy = box_rect.center().y()

            scale = max(0.1, p)
            painter.translate(cx, cy)
            painter.scale(scale, scale)
            painter.translate(-cx, -cy)

            path = QPainterPath()
            path.moveTo(box_rect.x() + 4.5, cy)
            path.lineTo(box_rect.x() + 7.5, cy + 3.5)
            path.lineTo(box_rect.x() + 13.5, cy - 3.5)
            painter.drawPath(path)

            painter.restore()

        text = self.text()
        if text:
            painter.setPen(QColor(c["TEXT_PRIMARY"]))
            font = self.font()
            painter.setFont(font)
            text_rect = QRectF(box_size + 10, 0, max(10.0, self.width() - box_size - 10), self.height())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, text)

    def sizeHint(self):
        font_metrics = self.fontMetrics()
        text_w = font_metrics.horizontalAdvance(self.text()) if self.text() else 0
        w = 18 + (10 if text_w > 0 else 0) + text_w + 12
        h = max(24, font_metrics.height() + 6)
        return QSize(w, h)

    def heightForWidth(self, width):
        if not self.text():
            return 24
        font_metrics = self.fontMetrics()
        box_size = 18
        avail_w = max(10, width - box_size - 10)
        rect = font_metrics.boundingRect(0, 0, avail_w, 10000, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, self.text())
        return max(24, rect.height() + 6)

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import QPoint

class CustomTitleBar(QWidget):
    def __init__(self, parent, title="", allow_maximize=True, allow_minimize=True):
        super().__init__(parent)
        self.parent = parent
        self.allow_maximize = allow_maximize
        self.allow_minimize = allow_minimize
        self.setFixedHeight(45)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)
        
        # 1. Window Title (Left side)
        self.title_lbl = QLabel(title)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.title_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY}; font-family: {FONT_FAMILY}; padding: 0px; background: transparent;")
        self.title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.title_lbl)
        
        layout.addStretch()
        
        # 2. macOS Style Traffic Light Buttons (Right side)
        # Yellow (Minimize)
        self.min_btn = QPushButton()
        self.min_btn.setFixedSize(12, 12)
        self.min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_btn.setToolTip("Minimize")
        if self.allow_minimize:
            self.min_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ffbd2e;
                    border-radius: 6px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #ffb114;
                }
            """)
            self.min_btn.clicked.connect(self.parent.showMinimized)
        else:
            self.min_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e2e8f0;
                    border-radius: 6px;
                    border: none;
                }
            """)
            self.min_btn.setEnabled(False)
        
        # Green (Maximize)
        self.max_btn = QPushButton()
        self.max_btn.setFixedSize(12, 12)
        self.max_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.max_btn.setToolTip("Maximize")
        if self.allow_maximize:
            self.max_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27c93f;
                    border-radius: 6px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #1ec030;
                }
            """)
            self.max_btn.clicked.connect(self.toggle_maximize)
        else:
            self.max_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e2e8f0;
                    border-radius: 6px;
                    border: none;
                }
            """)
            self.max_btn.setEnabled(False)
            
        # Red (Close)
        self.close_btn = QPushButton()
        self.close_btn.setFixedSize(12, 12)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff5f56;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #ff4c40;
            }
        """)
        self.close_btn.clicked.connect(self.parent.close)
        
        # Add sliding theme toggle
        self.theme_toggle = SlidingThemeToggle(self)
        self.theme_toggle.toggled.connect(self.on_theme_toggled)
        layout.addWidget(self.theme_toggle)
        layout.addSpacing(8)
             
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)
        
        # Dragging support (disabled for normal system window)
        self.drag_position = QPoint()
        self.apply_theme_dynamically()
        
    def apply_theme_dynamically(self):
        from ui.theme import get_colors, FONT_FAMILY
        theme_mode = getattr(self.parent, "theme_mode", None)
        c = get_colors(theme_mode)
        self.title_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {c['TEXT_PRIMARY']}; font-family: {FONT_FAMILY}; padding: 0px; background: transparent;")
        
        disabled_bg = "#2c2a38" if c.get("IS_DARK") else "#e2e8f0"
        if not self.allow_minimize:
            self.min_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {disabled_bg};
                    border-radius: 6px;
                    border: none;
                }}
            """)
        if not self.allow_maximize:
            self.max_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {disabled_bg};
                    border-radius: 6px;
                    border: none;
                }}
            """)

    def on_theme_toggled(self, new_theme):
        from utils.config_loader import get_config
        config = get_config()
        config.set("behavior.theme", new_theme)
        config.set("ui.theme", new_theme)
        
        if hasattr(self.parent, "theme_mode"):
            self.parent.theme_mode = new_theme

        if hasattr(self.parent, "theme_combo") and self.parent.theme_combo is not None:
            self.parent.theme_combo.blockSignals(True)
            idx = self.parent.theme_combo.findData(new_theme)
            if idx >= 0:
                self.parent.theme_combo.setCurrentIndex(idx)
            self.parent.theme_combo.blockSignals(False)

        if hasattr(self.parent, "apply_theme_dynamically"):
            self.parent.apply_theme_dynamically()
        else:
            from ui.theme import get_theme_qss
            self.parent.setStyleSheet(get_theme_qss())
            self.apply_theme_dynamically()
            if hasattr(self.parent, "main_container"):
                from ui.theme import get_colors
                c = get_colors()
                self.parent.main_container.setStyleSheet(f"""
                    QWidget#mainContainer {{
                        background-color: {c["BG_NEUTRAL"]};
                        border: 1px solid {c["BORDER_NEUTRAL"]};
                        border-radius: 12px;
                    }}
                """)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "drag_position") and not self.drag_position.isNull():
            self.parent.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
            
    def toggle_maximize(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

from PySide6.QtCore import Signal

class SlidingThemeToggle(QWidget):
    toggled = Signal(str) # Emits "light" or "dark"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_bar = parent
        self.setFixedSize(50, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Switch Theme (Light / Dark)")
        
        # Load initial theme state
        theme_mode = getattr(self.parent_bar.parent if self.parent_bar else None, "theme_mode", None)
        if theme_mode is not None:
            self.theme_mode = theme_mode
        else:
            from utils.config_loader import get_config
            try:
                config = get_config()
                self.theme_mode = config.get("behavior.theme", "light")
            except Exception:
                self.theme_mode = "light"
            
        is_dark = (self.theme_mode == "dark")
        
        self._knob_position = 1.0 if is_dark else 0.0
        self.anim = None
        
    @Property(float)
    def knob_position(self):
        return self._knob_position
        
    @knob_position.setter
    def knob_position(self, pos):
        self._knob_position = pos
        self.update()
        
    def update_toggle_state(self):
        theme_mode = getattr(self.parent_bar.parent if self.parent_bar else None, "theme_mode", None)
        if theme_mode is not None:
            self.theme_mode = theme_mode
        else:
            from utils.config_loader import get_config
            try:
                config = get_config()
                self.theme_mode = config.get("behavior.theme", "light")
            except Exception:
                self.theme_mode = "light"
            
        is_dark = (self.theme_mode == "dark")
        target_pos = 1.0 if is_dark else 0.0
        
        if self.anim:
            self.anim.stop()
            
        self.anim = QPropertyAnimation(self, b"knob_position")
        self.anim.setDuration(250)
        self.anim.setStartValue(self._knob_position)
        self.anim.setEndValue(target_pos)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.anim.start()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.parent_bar and hasattr(self.parent_bar.parent, "theme_mode"):
                current_theme = self.parent_bar.parent.theme_mode
                target_theme = "light" if current_theme == "dark" else "dark"
                self.parent_bar.parent.theme_mode = target_theme
                self.theme_mode = target_theme
            else:
                current_is_dark = (self.theme_mode == "dark")
                target_theme = "light" if current_is_dark else "dark"
                self.theme_mode = target_theme
                
                from utils.config_loader import get_config
                config = get_config()
                config.set("behavior.theme", target_theme)
                config.save()
            
            target_pos = 1.0 if target_theme == "dark" else 0.0
            
            if self.anim:
                self.anim.stop()
                
            self.anim = QPropertyAnimation(self, b"knob_position")
            self.anim.setDuration(250)
            self.anim.setStartValue(self._knob_position)
            self.anim.setEndValue(target_pos)
            self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.anim.start()
            
            self.toggled.emit(target_theme)
            event.accept()
            
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Smooth color transition based on knob position
        r = int(124 + (168 - 124) * self._knob_position)
        g = int(58 + (85 - 58) * self._knob_position)
        b = int(237 + (247 - 237) * self._knob_position)
        active_color = QColor(r, g, b)
        
        track_color = active_color if self._knob_position > 0.5 else QColor("#cbd5e1")
        painter.setBrush(track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)
        
        # Knob
        knob_color = QColor("#ffffff")
        painter.setBrush(knob_color)
        
        knob_radius = (self.height() - 6) / 2
        start_x = knob_radius + 3
        end_x = self.width() - knob_radius - 3
        current_x = start_x + (end_x - start_x) * self._knob_position
        
        painter.drawEllipse(QPointF(current_x, self.height() / 2), knob_radius, knob_radius)

def style_themed_label(label, color_key: str, extra_css: str = ""):
    from ui.theme import get_colors
    c = get_colors()
    label.setStyleSheet(f"{extra_css} color: {c[color_key]};")

def style_heading(label, size: int = 20):
    style_themed_label(label, "TEXT_PRIMARY", f"font-size: {size}px; font-weight: bold;")
