"""
Animated Authentication Result Overlays for FaceGATE-Linux.

Provides premium animated success (green checkmark morph) and failure
(red shake + pulse) overlays that display briefly before the auth dialog
closes, replacing the abrupt instant-close behavior.

Usage:
    from ui.auth_overlays import AuthSuccessOverlay, AuthFailureOverlay
    overlay = AuthSuccessOverlay(parent_widget)
    overlay.show_and_dismiss(callback=lambda: dialog.accept())
"""

import math
from PySide6.QtWidgets import QWidget, QLabel
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPointF, QRectF, Property, Signal
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPainterPath, QFont, QRadialGradient


class AuthSuccessOverlay(QWidget):
    """
    Animated green checkmark overlay with expanding circle, checkmark draw animation,
    particle burst, and expanding ring ripple for premium feel.
    Displays for 900ms before calling the dismiss callback.
    """
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0.0
        self._glow_opacity = 0.0
        self.anim = None
        self.glow_anim = None
        self.is_dark = False

        try:
            from utils.config_loader import get_config
            self.is_dark = get_config().get("behavior.theme", "light") == "dark"
        except Exception:
            pass

        self.setFixedSize(parent.width() if parent else 400, parent.height() if parent else 300)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        # Particle burst data: (angle, speed, size)
        import random
        self._particles = []
        for _ in range(12):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(40, 90)
            size = random.uniform(3, 6)
            self._particles.append((angle, speed, size))

    @Property(float)
    def draw_progress(self):
        return self._progress

    @draw_progress.setter
    def draw_progress(self, val):
        self._progress = val
        self.update()

    @Property(float)
    def glow_opacity(self):
        return self._glow_opacity

    @glow_opacity.setter
    def glow_opacity(self, val):
        self._glow_opacity = val
        self.update()

    def show_and_dismiss(self, callback=None, delay_ms=900):
        """Shows the success animation and calls callback after delay."""
        self.callback = callback
        self.show()
        self.raise_()

        # Circle + checkmark draw animation
        self.anim = QPropertyAnimation(self, b"draw_progress")
        self.anim.setDuration(600)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.anim.start()

        # Glow pulse
        self.glow_anim = QPropertyAnimation(self, b"glow_opacity")
        self.glow_anim.setDuration(500)
        self.glow_anim.setStartValue(0.0)
        self.glow_anim.setEndValue(0.6)
        self.glow_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.glow_anim.start()

        QTimer.singleShot(delay_ms, self._dismiss)

    def _dismiss(self):
        self.finished.emit()
        if self.callback:
            self.callback()
        self.hide()
        self.deleteLater()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0
        p = max(0.0, min(1.0, self._progress))

        # Semi-transparent backdrop
        backdrop = QColor("#0a0a0f" if self.is_dark else "#ffffff")
        backdrop.setAlphaF(0.75 * p)
        painter.fillRect(0, 0, w, h, backdrop)

        # Glow circle
        if self._glow_opacity > 0.01:
            glow_radius = 80 * p
            gradient = QRadialGradient(QPointF(cx, cy), glow_radius)
            glow_color = QColor("#10b981")
            glow_color.setAlphaF(self._glow_opacity * 0.3)
            gradient.setColorAt(0, glow_color)
            glow_color.setAlphaF(0)
            gradient.setColorAt(1, glow_color)
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

        # Green circle (scales up)
        circle_radius = 36 * p
        circle_color = QColor("#10b981")
        circle_color.setAlphaF(0.95)
        painter.setBrush(QBrush(circle_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), circle_radius, circle_radius)

        # Checkmark (draws progressively after circle is 40% complete)
        if p > 0.4:
            check_p = min(1.0, (p - 0.4) / 0.6)
            painter.setPen(QPen(QColor("#ffffff"), 3.5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)

            # Checkmark path points (relative to center)
            p1 = QPointF(cx - 14, cy + 1)
            p2 = QPointF(cx - 4, cy + 11)
            p3 = QPointF(cx + 14, cy - 9)

            path = QPainterPath()
            if check_p <= 0.5:
                # First stroke: p1 -> p2
                t = check_p / 0.5
                mid = QPointF(p1.x() + (p2.x() - p1.x()) * t, p1.y() + (p2.y() - p1.y()) * t)
                path.moveTo(p1)
                path.lineTo(mid)
            else:
                # Full first stroke + partial second
                t = (check_p - 0.5) / 0.5
                mid = QPointF(p2.x() + (p3.x() - p2.x()) * t, p2.y() + (p3.y() - p2.y()) * t)
                path.moveTo(p1)
                path.lineTo(p2)
                path.lineTo(mid)

            painter.drawPath(path)

        # Particle burst (scatter outward after 50% progress)
        if p > 0.5:
            particle_t = (p - 0.5) / 0.5
            for angle, speed, size in self._particles:
                dist = speed * particle_t
                px = cx + math.cos(angle) * dist
                py = cy + math.sin(angle) * dist
                particle_alpha = max(0.0, 1.0 - particle_t * 1.3)
                particle_color = QColor("#10b981")
                particle_color.setAlphaF(particle_alpha * 0.7)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(particle_color))
                painter.drawEllipse(QPointF(px, py), size * (1 - particle_t * 0.5), size * (1 - particle_t * 0.5))

        # Expanding ring ripple
        if p > 0.6:
            ripple_t = (p - 0.6) / 0.4
            ripple_radius = 36 + 60 * ripple_t
            ripple_alpha = max(0.0, 0.5 - ripple_t * 0.6)
            ripple_color = QColor("#10b981")
            ripple_color.setAlphaF(ripple_alpha)
            ripple_pen = QPen(ripple_color, 2.0)
            painter.setPen(ripple_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), ripple_radius, ripple_radius)

        # "Authenticated" text
        if p > 0.7:
            text_alpha = min(1.0, (p - 0.7) / 0.3)
            text_color = QColor("#10b981")
            text_color.setAlphaF(text_alpha)
            painter.setPen(text_color)
            painter.setFont(QFont("Inter", 14, QFont.Weight.Bold))
            painter.drawText(QRectF(0, cy + 50, w, 30),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             "✓ Authenticated")


class AuthFailureOverlay(QWidget):
    """
    Animated red X overlay with shake animation and pulse effect.
    Displays for 1000ms before calling the dismiss callback.
    """
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0.0
        self._shake_offset = 0.0
        self.anim = None
        self.shake_anim = None
        self.is_dark = False

        try:
            from utils.config_loader import get_config
            self.is_dark = get_config().get("behavior.theme", "light") == "dark"
        except Exception:
            pass

        self.setFixedSize(parent.width() if parent else 400, parent.height() if parent else 300)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

    @Property(float)
    def draw_progress(self):
        return self._progress

    @draw_progress.setter
    def draw_progress(self, val):
        self._progress = val
        self.update()

    @Property(float)
    def shake_offset(self):
        return self._shake_offset

    @shake_offset.setter
    def shake_offset(self, val):
        self._shake_offset = val
        self.update()

    def show_and_dismiss(self, callback=None, delay_ms=1100):
        """Shows the failure animation and calls callback after delay."""
        self.callback = callback
        self.show()
        self.raise_()

        # X draw animation
        self.anim = QPropertyAnimation(self, b"draw_progress")
        self.anim.setDuration(500)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self.anim.start()

        # Shake animation (rapid oscillation)
        self.shake_anim = QPropertyAnimation(self, b"shake_offset")
        self.shake_anim.setDuration(400)
        self.shake_anim.setKeyValueAt(0.0, 0)
        self.shake_anim.setKeyValueAt(0.1, -12)
        self.shake_anim.setKeyValueAt(0.2, 12)
        self.shake_anim.setKeyValueAt(0.3, -10)
        self.shake_anim.setKeyValueAt(0.4, 10)
        self.shake_anim.setKeyValueAt(0.55, -7)
        self.shake_anim.setKeyValueAt(0.7, 7)
        self.shake_anim.setKeyValueAt(0.85, -3)
        self.shake_anim.setKeyValueAt(1.0, 0)
        self.shake_anim.start()

        QTimer.singleShot(delay_ms, self._dismiss)

    def _dismiss(self):
        self.finished.emit()
        if self.callback:
            self.callback()
        self.hide()
        self.deleteLater()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0 + self._shake_offset
        cy = h / 2.0
        p = max(0.0, min(1.0, self._progress))

        # Semi-transparent backdrop with red edge vignette
        backdrop = QColor("#0a0a0f" if self.is_dark else "#ffffff")
        backdrop.setAlphaF(0.75 * p)
        painter.fillRect(0, 0, w, h, backdrop)
        
        # Red vignette edge effect
        if p > 0.2:
            vignette_alpha = min(0.15, p * 0.15)
            for edge_dist in range(0, 30, 3):
                edge_color = QColor("#ef4444")
                edge_color.setAlphaF(vignette_alpha * (1 - edge_dist / 30.0))
                painter.setPen(QPen(edge_color, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(edge_dist, edge_dist, w - edge_dist * 2, h - edge_dist * 2)

        # Red glow
        if p > 0.1:
            glow_radius = 80 * p
            gradient = QRadialGradient(QPointF(cx, cy), glow_radius)
            glow_color = QColor("#ef4444")
            glow_color.setAlphaF(0.25 * p)
            gradient.setColorAt(0, glow_color)
            glow_color.setAlphaF(0)
            gradient.setColorAt(1, glow_color)
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy), glow_radius, glow_radius)

        # Red circle
        circle_radius = 36 * p
        circle_color = QColor("#ef4444")
        circle_color.setAlphaF(0.95)
        painter.setBrush(QBrush(circle_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), circle_radius, circle_radius)

        # X mark (two crossing lines, drawn progressively)
        if p > 0.3:
            x_p = min(1.0, (p - 0.3) / 0.7)
            painter.setPen(QPen(QColor("#ffffff"), 3.5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

            arm = 12
            # First diagonal: top-left to bottom-right
            if x_p <= 0.5:
                t = x_p / 0.5
                x1, y1 = cx - arm, cy - arm
                x2 = x1 + (2 * arm) * t
                y2 = y1 + (2 * arm) * t
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            else:
                t = (x_p - 0.5) / 0.5
                painter.drawLine(QPointF(cx - arm, cy - arm), QPointF(cx + arm, cy + arm))
                # Second diagonal: top-right to bottom-left
                x1, y1 = cx + arm, cy - arm
                x2 = x1 + (-2 * arm) * t
                y2 = y1 + (2 * arm) * t
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # "Access Denied" text
        if p > 0.6:
            text_alpha = min(1.0, (p - 0.6) / 0.4)
            text_color = QColor("#ef4444")
            text_color.setAlphaF(text_alpha)
            painter.setPen(text_color)
            painter.setFont(QFont("Inter", 14, QFont.Weight.Bold))
            painter.drawText(QRectF(0, cy + 50, w, 30),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             "✗ Access Denied")
