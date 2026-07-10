import os
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QRect, QVariantAnimation, QEasingCurve, QAbstractAnimation
from PySide6.QtWidgets import QSpinBox

# Purple & White light palette
BG_NEUTRAL = "#f5f3ff"
CARD_NEUTRAL = "#faf9fc"
BORDER_NEUTRAL = "#e9e7f1"
TEXT_PRIMARY = "#1e1b4b"
TEXT_SECONDARY = "#5c5770"

# Accents
ACCENT_PURPLE = "#7c3aed"
ACCENT_PURPLE_HOVER = "#6d28d9"
ACCENT_PURPLE_PRESSED = "#5b21b6"
SUCCESS_GREEN = "#10b981"
DANGER_RED = "#ef4444"
WARNING_AMBER = "#fbbf24"

FONT_FAMILY = 'Inter, "Cantarell", "Noto Sans", sans-serif'

def get_theme_qss() -> str:
    return f"""
        QDialog, QMainWindow {{
            background-color: {BG_NEUTRAL};
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
        }}
        QLabel {{
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
        }}
        QLineEdit {{
            background-color: #ffffff;
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 6px;
            padding: 8px 12px;
            color: {TEXT_PRIMARY};
            font-size: 13px;
            font-family: {FONT_FAMILY};
        }}
        QLineEdit:focus {{
            border: 1px solid {ACCENT_PURPLE};
        }}
        QPushButton {{
            background-color: {ACCENT_PURPLE};
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 13px;
            font-family: {FONT_FAMILY};
        }}
        QPushButton:hover {{
            background-color: {ACCENT_PURPLE_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {ACCENT_PURPLE_PRESSED};
        }}
        QPushButton#cancelBtn {{
            background-color: #f1f5f9;
            color: {TEXT_PRIMARY};
            border: 1px solid {BORDER_NEUTRAL};
        }}
        QPushButton#cancelBtn:hover {{
            background-color: #e2e8f0;
        }}
        QListWidget {{
            background-color: {CARD_NEUTRAL};
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 8px;
            color: {TEXT_PRIMARY};
            font-size: 13px;
            font-family: {FONT_FAMILY};
            padding: 4px;
        }}
        QListWidget::item {{
            padding: 8px;
            border-radius: 4px;
            color: {TEXT_PRIMARY};
        }}
        QListWidget::item:hover {{
            background-color: #f3e8ff;
        }}
        QListWidget::item:selected {{
            background-color: {ACCENT_PURPLE};
            color: white;
        }}
        QTreeWidget {{
            background-color: {CARD_NEUTRAL};
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 8px;
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 13px;
            padding: 4px;
        }}
        QTreeWidget::item {{
            padding: 6px;
            color: {TEXT_PRIMARY};
        }}
        QTreeWidget::item:hover {{
            background-color: #f3e8ff;
        }}
        QTreeWidget::item:selected {{
            background-color: {ACCENT_PURPLE};
            color: white;
        }}
        QHeaderView::section {{
            background-color: #f1f5f9;
            color: {TEXT_SECONDARY};
            padding: 6px;
            border: 1px solid {BORDER_NEUTRAL};
            font-weight: bold;
        }}
        QComboBox {{
            background-color: #ffffff;
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 6px;
            padding: 6px 12px;
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QComboBox:focus {{
            border: 1px solid {ACCENT_PURPLE};
        }}
        QSpinBox {{
            background-color: #ffffff;
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 6px;
            padding: 6px 12px;
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QSpinBox:focus {{
            border: 1px solid {ACCENT_PURPLE};
        }}
        QCheckBox {{
            spacing: 8px;
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 4px;
            background-color: #ffffff;
        }}
        QCheckBox::indicator:checked {{
            background-color: {ACCENT_PURPLE};
            border: 1px solid {ACCENT_PURPLE};
        }}
        QProgressBar {{
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 6px;
            background-color: #f1f5f9;
            text-align: center;
            color: {TEXT_PRIMARY};
            font-weight: bold;
            height: 18px;
        }}
        QProgressBar::chunk {{
            background-color: {ACCENT_PURPLE};
            border-radius: 5px;
        }}
        QTableWidget {{
            background-color: {CARD_NEUTRAL};
            border: 1px solid {BORDER_NEUTRAL};
            gridline-color: {BORDER_NEUTRAL};
            color: {TEXT_PRIMARY};
            border-radius: 8px;
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QTableWidget::item {{
            padding: 6px;
            color: {TEXT_PRIMARY};
        }}
    """

def get_card_qss(importance: str = "normal") -> str:
    if importance == "danger":
        border_qss = f"border-left: 4px solid {DANGER_RED}; border-top: 1px solid {BORDER_NEUTRAL}; border-right: 1px solid {BORDER_NEUTRAL}; border-bottom: 1px solid {BORDER_NEUTRAL};"
    elif importance == "accent":
        border_qss = f"border-left: 4px solid {ACCENT_PURPLE}; border-top: 1px solid {BORDER_NEUTRAL}; border-right: 1px solid {BORDER_NEUTRAL}; border-bottom: 1px solid {BORDER_NEUTRAL};"
    else:
        border_qss = f"border: 1px solid {BORDER_NEUTRAL};"
        
    return f"""
        QWidget#card {{
            background-color: {CARD_NEUTRAL};
            {border_qss}
            border-radius: 8px;
        }}
        QLabel {{
            border: none;
            background-color: transparent;
            color: {TEXT_PRIMARY};
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
