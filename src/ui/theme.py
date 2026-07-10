import os
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt, QRect

# Neutral Charcoal palette
BG_NEUTRAL = "#0a0a0c"
CARD_NEUTRAL = "#121216"
BORDER_NEUTRAL = "#1f1f24"
TEXT_PRIMARY = "#f8fafc"
TEXT_SECONDARY = "#94a3b8"

# Accents
ACCENT_CYAN = "#0ea5e9"
SUCCESS_GREEN = "#10b981"
DANGER_RED = "#ef4444"
WARNING_AMBER = "#f59e0b"

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
            background-color: #1a1a20;
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 6px;
            padding: 8px 12px;
            color: #ffffff;
            font-size: 13px;
            font-family: {FONT_FAMILY};
        }}
        QLineEdit:focus {{
            border: 1px solid {ACCENT_CYAN};
        }}
        QPushButton {{
            background-color: {ACCENT_CYAN};
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 13px;
            font-family: {FONT_FAMILY};
        }}
        QPushButton:hover {{
            background-color: #0284c7;
        }}
        QPushButton:pressed {{
            background-color: #0369a1;
        }}
        QPushButton#cancelBtn {{
            background-color: #27272a;
            color: {TEXT_PRIMARY};
        }}
        QPushButton#cancelBtn:hover {{
            background-color: #3f3f46;
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
        }}
        QListWidget::item:hover {{
            background-color: #1e1e24;
        }}
        QListWidget::item:selected {{
            background-color: {ACCENT_CYAN};
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
        }}
        QTreeWidget::item:hover {{
            background-color: #1e1e24;
        }}
        QTreeWidget::item:selected {{
            background-color: {ACCENT_CYAN};
            color: white;
        }}
        QHeaderView::section {{
            background-color: #1a1a20;
            color: {TEXT_SECONDARY};
            padding: 6px;
            border: 1px solid {BORDER_NEUTRAL};
            font-weight: bold;
        }}
        QComboBox {{
            background-color: #1a1a20;
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 6px;
            padding: 6px 12px;
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QComboBox:focus {{
            border: 1px solid {ACCENT_CYAN};
        }}
        QSpinBox {{
            background-color: #1a1a20;
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 6px;
            padding: 6px 12px;
            color: {TEXT_PRIMARY};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QSpinBox:focus {{
            border: 1px solid {ACCENT_CYAN};
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
            background-color: #1a1a20;
        }}
        QCheckBox::indicator:checked {{
            background-color: {ACCENT_CYAN};
            border: 1px solid {ACCENT_CYAN};
        }}
        QProgressBar {{
            border: 1px solid {BORDER_NEUTRAL};
            border-radius: 6px;
            background-color: #1a1a20;
            text-align: center;
            color: #ffffff;
            font-weight: bold;
            height: 18px;
        }}
        QProgressBar::chunk {{
            background-color: {ACCENT_CYAN};
            border-radius: 5px;
        }}
    """

def get_card_qss(importance: str = "normal") -> str:
    if importance == "danger":
        border_qss = f"border-left: 4px solid {DANGER_RED}; border-top: 1px solid {BORDER_NEUTRAL}; border-right: 1px solid {BORDER_NEUTRAL}; border-bottom: 1px solid {BORDER_NEUTRAL};"
    elif importance == "accent":
        border_qss = f"border-left: 4px solid {ACCENT_CYAN}; border-top: 1px solid {BORDER_NEUTRAL}; border-right: 1px solid {BORDER_NEUTRAL}; border-bottom: 1px solid {BORDER_NEUTRAL};"
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
