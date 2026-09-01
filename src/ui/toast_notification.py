"""
Toast Notification System for FaceGATE-Linux.

Provides sleek, animated, non-blocking toast notifications that slide in
from the bottom-right corner and auto-dismiss. Replaces modal QMessageBox
popups for a more modern UX.

Usage:
    from ui.toast_notification import ToastManager
    ToastManager.show_toast(parent_widget, "Message", severity="success")
"""

import logging
from typing import Optional
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QPushButton, QApplication, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRect, QRectF, Property, Signal
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QFont, QGuiApplication


# Severity color definitions
TOAST_COLORS = {
    "info": {
        "bg_dark": "#1a1f36", "bg_light": "#f0f4ff",
        "border_dark": "#3b82f6", "border_light": "#3b82f6",
        "text_dark": "#e0e7ff", "text_light": "#1e3a5f",
        "icon": "ℹ️", "accent": "#3b82f6"
    },
    "success": {
        "bg_dark": "#0d2818", "bg_light": "#f0fdf4",
        "border_dark": "#10b981", "border_light": "#10b981",
        "text_dark": "#d1fae5", "text_light": "#064e3b",
        "icon": "✅", "accent": "#10b981"
    },
    "warning": {
        "bg_dark": "#2d261e", "bg_light": "#fffbeb",
        "border_dark": "#f59e0b", "border_light": "#f59e0b",
        "text_dark": "#fef3c7", "text_light": "#78350f",
        "icon": "⚠️", "accent": "#f59e0b"
    },
    "error": {
        "bg_dark": "#2d1b1b", "bg_light": "#fef2f2",
        "border_dark": "#ef4444", "border_light": "#ef4444",
        "text_dark": "#fecaca", "text_light": "#7f1d1d",
        "icon": "❌", "accent": "#ef4444"
    }
}

# Global list of active toasts for stacking
_active_toasts: list = []


class Toast(QWidget):
    """
    A single animated toast notification widget.
    Slides in from the right edge, displays for a duration, then fades out.
    """
    dismissed = Signal()

    TOAST_WIDTH = 380
    TOAST_HEIGHT = 72
    MARGIN = 18
    SPACING = 8

    def __init__(self, parent, message: str, severity: str = "info",
                 duration_ms: int = 4000, title: Optional[str] = None):
        # Use the top-level window as parent for correct positioning
        top_level = parent.window() if parent else None
        super().__init__(top_level)

        self.message = message
        self.severity = severity
        self.duration_ms = duration_ms
        self.title = title
        self._opacity = 0.0

        # Determine theme mode
        try:
            from utils.config_loader import get_config
            cfg_theme = get_config().get("behavior.theme", "light")
            self.is_dark = cfg_theme == "dark"
        except Exception:
            self.is_dark = False

        self.setFixedSize(self.TOAST_WIDTH, self.TOAST_HEIGHT)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.dismiss)

        self._anim = None

    @Property(float)
    def toast_opacity(self):
        return self._opacity

    @toast_opacity.setter
    def toast_opacity(self, val):
        self._opacity = val
        self.opacity_effect.setOpacity(val)

    def show_toast(self):
        # Position at bottom-right of parent window
        parent = self.parentWidget()
        if parent:
            parent_geom = parent.geometry()
            target_x = parent_geom.width() - self.TOAST_WIDTH - self.MARGIN
            target_y = parent_geom.height() - self.TOAST_HEIGHT - self.MARGIN
        else:
            target_x = 100
            target_y = 100

        # Start slightly below final position
        start_y = target_y + 20
        self.move(target_x, start_y)
        self.show()
        self.raise_()


    def start_dismiss(self):
        """Animates the toast out of view and cleans up."""
        self.progress_timer.stop()

        self.fade_out_anim = QPropertyAnimation(self, b"toast_opacity")
        self.fade_out_anim.setDuration(300)
        self.fade_out_anim.setStartValue(self._opacity)
        self.fade_out_anim.setEndValue(0.0)
        self.fade_out_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.fade_out_anim.finished.connect(self._cleanup)
        self.fade_out_anim.start()

    def _cleanup(self):
        global _active_toasts
        if self in _active_toasts:
            _active_toasts.remove(self)
        self._reposition_all()
        self.dismissed.emit()
        self.deleteLater()

    def _update_progress(self):
        if self.duration_ms > 0:
            self._progress = max(0.0, self._progress - (50.0 / self.duration_ms))
            self.update()

    def _reposition_all(self):
        """Repositions all active toasts to stack vertically."""
        parent = self.parentWidget()
        if not parent:
            return

        parent_rect = parent.rect()
        base_x = parent_rect.width() - self.TOAST_WIDTH - self.MARGIN
        base_y = parent_rect.height() - self.MARGIN

        for i, toast in enumerate(reversed(_active_toasts)):
            y = base_y - (i + 1) * (self.TOAST_HEIGHT + self.SPACING)
            toast.move(base_x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = TOAST_COLORS.get(self.severity, TOAST_COLORS["info"])
        mode = "dark" if self.is_dark else "light"

        bg_color = QColor(colors[f"bg_{mode}"])
        border_color = QColor(colors[f"border_{mode}"])
        text_color = QColor(colors[f"text_{mode}"])
        accent_color = QColor(colors["accent"])

        # Background rounded rect
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, 12, 12)
        painter.fillPath(path, QBrush(bg_color))

        # Left accent bar
        accent_path = QPainterPath()
        accent_path.addRoundedRect(0, 0, 4, self.height(), 2, 2)
        painter.fillPath(accent_path, QBrush(accent_color))

        # Border
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 12, 12)

        # Icon
        icon = colors["icon"]
        painter.setFont(QFont("sans-serif", 16))
        painter.setPen(text_color)
        painter.drawText(QRect(14, 0, 32, self.height()), Qt.AlignmentFlag.AlignVCenter, icon)

        # Text
        text_x = 50
        painter.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        painter.setPen(text_color)

        if self.title:
            painter.drawText(QRect(text_x, 8, self.width() - text_x - 16, 22),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title)
            painter.setFont(QFont("Inter", 11))
            painter.setPen(QColor(text_color.red(), text_color.green(), text_color.blue(), 180))
            painter.drawText(QRect(text_x, 30, self.width() - text_x - 16, 26),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.message)
        else:
            painter.drawText(QRect(text_x, 0, self.width() - text_x - 40, self.height()),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.message)

        # Close button (× icon) — drawn as small text
        close_color = QColor(text_color)
        close_color.setAlphaF(0.5)
        painter.setPen(close_color)
        painter.setFont(QFont("Inter", 13))
        painter.drawText(QRect(self.width() - 36, 0, 28, self.height()),
                         Qt.AlignmentFlag.AlignCenter, "×")

        # Progress bar at bottom
        if self._progress < 1.0:
            progress_h = 2
            progress_y = self.height() - progress_h - 2
            progress_w = int((self.width() - 24) * self._progress)

            painter.setPen(Qt.PenStyle.NoPen)
            # Track
            track_color = QColor(accent_color)
            track_color.setAlphaF(0.15)
            painter.setBrush(QBrush(track_color))
            painter.drawRoundedRect(12, progress_y, self.width() - 24, progress_h, 1, 1)
            # Fill
            painter.setBrush(QBrush(accent_color))
            painter.drawRoundedRect(12, progress_y, progress_w, progress_h, 1, 1)

    def mousePressEvent(self, event):
        """Dismiss on click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dismiss_timer.stop()
            self.start_dismiss()
            event.accept()

    def enterEvent(self, event):
        """Pause auto-dismiss on hover."""
        if not self._paused and self.dismiss_timer.isActive():
            self._paused = True
            self._remaining_ms = max(0, self.dismiss_timer.remainingTime())
            self.dismiss_timer.stop()
            self.progress_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Resume auto-dismiss on hover exit."""
        if self._paused:
            self._paused = False
            if hasattr(self, '_remaining_ms') and self._remaining_ms > 0:
                self.dismiss_timer.start(self._remaining_ms)
                self.progress_timer.start(50)
        super().leaveEvent(event)


class ToastManager:
    """
    Static manager for creating and displaying toast notifications.
    
    Usage:
        ToastManager.show_toast(parent, "Settings saved!", severity="success")
        ToastManager.show_info(parent, "Processing...")
        ToastManager.show_success(parent, "Done!")
        ToastManager.show_warning(parent, "Low disk space")
        ToastManager.show_error(parent, "Connection failed")
    """

    @staticmethod
    def show_toast(parent: QWidget, message: str, severity: str = "info",
                   duration_ms: int = 4000, title: Optional[str] = None) -> Toast:
        toast = Toast(parent, message, severity, duration_ms, title)
        toast.show_toast()
        return toast

    @staticmethod
    def show_info(parent: QWidget, message: str, duration_ms: int = 4000, title: Optional[str] = None) -> Toast:
        return ToastManager.show_toast(parent, message, "info", duration_ms, title)

    @staticmethod
    def show_success(parent: QWidget, message: str, duration_ms: int = 3000, title: Optional[str] = None) -> Toast:
        return ToastManager.show_toast(parent, message, "success", duration_ms, title)

    @staticmethod
    def show_warning(parent: QWidget, message: str, duration_ms: int = 5000, title: Optional[str] = None) -> Toast:
        return ToastManager.show_toast(parent, message, "warning", duration_ms, title)

class BiometricHUD(QWidget):
    """
    Ultra-sleek, minimal floating glassmorphic pill notification displayed at the top-center
    of the active desktop screen when an application lock/unlock transition occurs.
    """
    HUD_WIDTH = 260
    HUD_HEIGHT = 44

    def __init__(self, message: str, icon: str = "🛡️", is_success: bool = True, duration_ms: int = 2500):
        super().__init__(None)
        self.message = message
        self.icon = icon
        self.is_success = is_success
        self.duration_ms = duration_ms
        self._opacity = 0.0

        self.setFixedSize(self.HUD_WIDTH, self.HUD_HEIGHT)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.opacity_effect)

        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.dismiss)

    @Property(float)
    def hud_opacity(self):
        return self._opacity

    @hud_opacity.setter
    def hud_opacity(self, val):
        self._opacity = val
        self.opacity_effect.setOpacity(val)

    def show_hud(self):
        # Center horizontally at top of primary screen
        app = QApplication.instance()
        if isinstance(app, (QApplication, QGuiApplication)):
            screen = app.primaryScreen()
            if screen:
                geom = screen.geometry()
                target_x = geom.x() + (geom.width() - self.HUD_WIDTH) // 2
                target_y = geom.y() + 40
                self.move(target_x, target_y - 20)

        self.show()
        self.raise_()

        # Slide down & fade in
        self.slide_in = QPropertyAnimation(self, b"pos")
        self.slide_in.setDuration(300)
        self.slide_in.setStartValue(QPoint(self.x(), self.y()))
        self.slide_in.setEndValue(QPoint(self.x(), self.y() + 20))
        self.slide_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.fade_in = QPropertyAnimation(self, b"hud_opacity")
        self.fade_in.setDuration(250)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.slide_in.start()
        self.fade_in.start()
        self.dismiss_timer.start(self.duration_ms)

    def dismiss(self):
        self.fade_out = QPropertyAnimation(self, b"hud_opacity")
        self.fade_out.setDuration(300)
        self.fade_out.setStartValue(self._opacity)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        self.fade_out.finished.connect(self.deleteLater)
        self.fade_out.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Translucent dark glassmorphism capsule
        bg_color = QColor(15, 23, 42, 230) if self.is_success else QColor(30, 10, 10, 235)
        border_color = QColor(16, 185, 129, 180) if self.is_success else QColor(239, 68, 68, 180)

        path = QPainterPath()
        path.addRoundedRect(1, 1, self.width() - 2, self.height() - 2, 22, 22)
        painter.fillPath(path, QBrush(bg_color))

        painter.setPen(QPen(border_color, 1.2))
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 22, 22)

        # Icon & Text
        painter.setFont(QFont("sans-serif", 13))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRect(14, 0, 28, self.height()), Qt.AlignmentFlag.AlignVCenter, self.icon)

        painter.setFont(QFont("Inter", 11, QFont.Weight.DemiBold))
        text_color = QColor(241, 245, 249)
        painter.setPen(text_color)
        painter.drawText(QRect(44, 0, self.width() - 56, self.height()),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.message)

    @classmethod
    def show_unlocked(cls, app_name: str):
        hud = cls(f"{app_name} Unlocked", icon="🛡️", is_success=True)
        hud.show_hud()
        return hud

    @classmethod
    def show_locked(cls, app_name: str):
        hud = cls(f"{app_name} Locked", icon="🔒", is_success=False)
        hud.show_hud()
        return hud

