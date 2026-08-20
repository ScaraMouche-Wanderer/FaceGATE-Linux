import os
import subprocess
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QPainterPath, QFont
from PySide6.QtCore import Qt, QRect, QRectF, QPointF, QSize, QVariantAnimation, QEasingCurve, QAbstractAnimation, Property, QPropertyAnimation, QModelIndex, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QSpinBox, QComboBox, QCheckBox, QStyledItemDelegate, QStyleOptionViewItem, QStyle, QListView, QFrame, QPushButton

# Global constants initialized to default light mode
BG_NEUTRAL = "#f5f4f2"
CARD_NEUTRAL = "#fdfcfb"
BORDER_NEUTRAL = "#ddd6cc"
TEXT_PRIMARY = "#1c1917"
TEXT_SECONDARY = "#57534e"
ACCENT_PURPLE = "#c2410c"
ACCENT_PURPLE_HOVER = "#9a3412"
ACCENT_PURPLE_PRESSED = "#7c2d12"
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

PALETTES = {
    "iron_ember": {
        "label": "Iron & Ember (Burnt Copper)",
        "dark": {
            "IS_DARK": True,
            "BG_NEUTRAL": "#14110d",
            "BG_SECONDARY": "#1e1a15",
            "CARD_NEUTRAL": "#211c17",
            "BORDER_NEUTRAL": "#3d352c",
            "TEXT_PRIMARY": "#f5f2ee",
            "TEXT_SECONDARY": "#d9d2c7",
            "HEADER_TEXT": "#fb923c",
            "ACCENT_PURPLE": "#f97316",
            "ACCENT_PURPLE_HOVER": "#fb923c",
            "ACCENT_PURPLE_PRESSED": "#ea580c",
            "WIDGET_BG": "#191510",
            "LIST_ITEM_HOVER": "#332c22",
            "HOVER_NEUTRAL": "#332c22",
            "CANCEL_BTN_BG": "#2a2419",
            "CANCEL_BTN_HOVER": "#3d3527",
            "SHADOW_COLOR": "rgba(0, 0, 0, 0.6)",
            "STATUS_HEADER_BG": "#241f18",
            "SIDEBAR_BG": "#191510",
            "SIDEBAR_HOVER_BG": "#332c22",
            "SIDEBAR_COLOR": "#d9d2c7",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#fbbf24"
        },
        "light": {
            "IS_DARK": False,
            "BG_NEUTRAL": "#f5f4f0",
            "BG_SECONDARY": "#ffffff",
            "CARD_NEUTRAL": "#ffffff",
            "BORDER_NEUTRAL": "#d9d2c7",
            "TEXT_PRIMARY": "#1c1917",
            "TEXT_SECONDARY": "#57534e",
            "HEADER_TEXT": "#9a3412",
            "ACCENT_PURPLE": "#c2410c",
            "ACCENT_PURPLE_HOVER": "#9a3412",
            "ACCENT_PURPLE_PRESSED": "#7c2d12",
            "WIDGET_BG": "#ffffff",
            "LIST_ITEM_HOVER": "#f5f4f0",
            "HOVER_NEUTRAL": "#f5f4f0",
            "CANCEL_BTN_BG": "#f5f4f0",
            "CANCEL_BTN_HOVER": "#e5ddd0",
            "SHADOW_COLOR": "rgba(194, 65, 12, 0.12)",
            "STATUS_HEADER_BG": "#f5f4f0",
            "SIDEBAR_BG": "#f3e7da",
            "SIDEBAR_HOVER_BG": "#e8d5bf",
            "SIDEBAR_COLOR": "#6b5b4a",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#f59e0b"
        }
    },
    "violet_slate": {
        "label": "Violet & Slate (Classic Purple)",
        "dark": {
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
            "SIDEBAR_BG": "#110f1c",
            "SIDEBAR_HOVER_BG": "#27223e",
            "SIDEBAR_COLOR": "#cbd5e1",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#fbbf24"
        },
        "light": {
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
            "SIDEBAR_BG": "#ede9fe",
            "SIDEBAR_HOVER_BG": "#e5dbff",
            "SIDEBAR_COLOR": "#4c4664",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#f59e0b"
        }
    },
    "amber_espresso": {
        "label": "Amber & Espresso (Warm Gold)",
        "dark": {
            "IS_DARK": True,
            "BG_NEUTRAL": "#16130e",
            "BG_SECONDARY": "#201c15",
            "CARD_NEUTRAL": "#241f18",
            "BORDER_NEUTRAL": "#42382b",
            "TEXT_PRIMARY": "#f7f3eb",
            "TEXT_SECONDARY": "#d6cbba",
            "HEADER_TEXT": "#fbbf24",
            "ACCENT_PURPLE": "#f59e0b",
            "ACCENT_PURPLE_HOVER": "#fbbf24",
            "ACCENT_PURPLE_PRESSED": "#d97706",
            "WIDGET_BG": "#1c1812",
            "LIST_ITEM_HOVER": "#362e22",
            "HOVER_NEUTRAL": "#362e22",
            "CANCEL_BTN_BG": "#2b241b",
            "CANCEL_BTN_HOVER": "#3d3326",
            "SHADOW_COLOR": "rgba(0, 0, 0, 0.6)",
            "STATUS_HEADER_BG": "#282218",
            "SIDEBAR_BG": "#1c1812",
            "SIDEBAR_HOVER_BG": "#3d3326",
            "SIDEBAR_COLOR": "#d6cbba",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#fbbf24"
        },
        "light": {
            "IS_DARK": False,
            "BG_NEUTRAL": "#faf7f0",
            "BG_SECONDARY": "#ffffff",
            "CARD_NEUTRAL": "#ffffff",
            "BORDER_NEUTRAL": "#e5dec9",
            "TEXT_PRIMARY": "#262118",
            "TEXT_SECONDARY": "#615745",
            "HEADER_TEXT": "#b45309",
            "ACCENT_PURPLE": "#d97706",
            "ACCENT_PURPLE_HOVER": "#b45309",
            "ACCENT_PURPLE_PRESSED": "#92400e",
            "WIDGET_BG": "#ffffff",
            "LIST_ITEM_HOVER": "#faf7f0",
            "HOVER_NEUTRAL": "#faf7f0",
            "CANCEL_BTN_BG": "#faf7f0",
            "CANCEL_BTN_HOVER": "#eee6d3",
            "SHADOW_COLOR": "rgba(217, 119, 6, 0.12)",
            "STATUS_HEADER_BG": "#faf7f0",
            "SIDEBAR_BG": "#eee6d3",
            "SIDEBAR_HOVER_BG": "#e5dec9",
            "SIDEBAR_COLOR": "#615745",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#f59e0b"
        }
    },
    "emerald_obsidian": {
        "label": "Emerald & Obsidian (Green)",
        "dark": {
            "IS_DARK": True,
            "BG_NEUTRAL": "#06140e",
            "BG_SECONDARY": "#0c1f17",
            "CARD_NEUTRAL": "#0f261d",
            "BORDER_NEUTRAL": "#1b4233",
            "TEXT_PRIMARY": "#ecfdf5",
            "TEXT_SECONDARY": "#a7f3d0",
            "HEADER_TEXT": "#34d399",
            "ACCENT_PURPLE": "#10b981",
            "ACCENT_PURPLE_HOVER": "#34d399",
            "ACCENT_PURPLE_PRESSED": "#059669",
            "WIDGET_BG": "#0a1a13",
            "LIST_ITEM_HOVER": "#17382b",
            "HOVER_NEUTRAL": "#17382b",
            "CANCEL_BTN_BG": "#122b20",
            "CANCEL_BTN_HOVER": "#1a3d2e",
            "SHADOW_COLOR": "rgba(0, 0, 0, 0.6)",
            "STATUS_HEADER_BG": "#122e22",
            "SIDEBAR_BG": "#0a1a13",
            "SIDEBAR_HOVER_BG": "#1a3d2e",
            "SIDEBAR_COLOR": "#a7f3d0",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#fbbf24"
        },
        "light": {
            "IS_DARK": False,
            "BG_NEUTRAL": "#f4fbf7",
            "BG_SECONDARY": "#ffffff",
            "CARD_NEUTRAL": "#ffffff",
            "BORDER_NEUTRAL": "#d1fae5",
            "TEXT_PRIMARY": "#064e3b",
            "TEXT_SECONDARY": "#047857",
            "HEADER_TEXT": "#047857",
            "ACCENT_PURPLE": "#059669",
            "ACCENT_PURPLE_HOVER": "#047857",
            "ACCENT_PURPLE_PRESSED": "#065f46",
            "WIDGET_BG": "#ffffff",
            "LIST_ITEM_HOVER": "#f0fdf4",
            "HOVER_NEUTRAL": "#f0fdf4",
            "CANCEL_BTN_BG": "#e6f7ed",
            "CANCEL_BTN_HOVER": "#d1fae5",
            "SHADOW_COLOR": "rgba(5, 150, 105, 0.12)",
            "STATUS_HEADER_BG": "#e6f7ed",
            "SIDEBAR_BG": "#e6f7ed",
            "SIDEBAR_HOVER_BG": "#d1fae5",
            "SIDEBAR_COLOR": "#065f46",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#f59e0b"
        }
    },
    "cyber_neon": {
        "label": "Cyber Neon (Electric Cyan)",
        "dark": {
            "IS_DARK": True,
            "BG_NEUTRAL": "#0a0a0f",
            "BG_SECONDARY": "#0f0f1a",
            "CARD_NEUTRAL": "#12121f",
            "BORDER_NEUTRAL": "#1e1e3a",
            "TEXT_PRIMARY": "#e8eaf6",
            "TEXT_SECONDARY": "#9fa8da",
            "HEADER_TEXT": "#00d4ff",
            "ACCENT_PURPLE": "#00b8d4",
            "ACCENT_PURPLE_HOVER": "#00e5ff",
            "ACCENT_PURPLE_PRESSED": "#0097a7",
            "WIDGET_BG": "#0d0d18",
            "LIST_ITEM_HOVER": "#1a1a30",
            "HOVER_NEUTRAL": "#1a1a30",
            "CANCEL_BTN_BG": "#161625",
            "CANCEL_BTN_HOVER": "#222238",
            "SHADOW_COLOR": "rgba(0, 212, 255, 0.15)",
            "STATUS_HEADER_BG": "#141422",
            "SIDEBAR_BG": "#0d0d18",
            "SIDEBAR_HOVER_BG": "#1e1e34",
            "SIDEBAR_COLOR": "#9fa8da",
            "SUCCESS_GREEN": "#00e676",
            "DANGER_RED": "#ff1744",
            "WARNING_AMBER": "#ffea00"
        },
        "light": {
            "IS_DARK": False,
            "BG_NEUTRAL": "#f0faff",
            "BG_SECONDARY": "#ffffff",
            "CARD_NEUTRAL": "#ffffff",
            "BORDER_NEUTRAL": "#b2ebf2",
            "TEXT_PRIMARY": "#0d2137",
            "TEXT_SECONDARY": "#37474f",
            "HEADER_TEXT": "#00838f",
            "ACCENT_PURPLE": "#0097a7",
            "ACCENT_PURPLE_HOVER": "#00838f",
            "ACCENT_PURPLE_PRESSED": "#006064",
            "WIDGET_BG": "#ffffff",
            "LIST_ITEM_HOVER": "#e0f7fa",
            "HOVER_NEUTRAL": "#e0f7fa",
            "CANCEL_BTN_BG": "#e0f7fa",
            "CANCEL_BTN_HOVER": "#b2ebf2",
            "SHADOW_COLOR": "rgba(0, 151, 167, 0.12)",
            "STATUS_HEADER_BG": "#e0f7fa",
            "SIDEBAR_BG": "#b2ebf2",
            "SIDEBAR_HOVER_BG": "#80deea",
            "SIDEBAR_COLOR": "#006064",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#f59e0b"
        }
    },
    "nordic_frost": {
        "label": "Nordic Frost (Deep Navy & Ice)",
        "dark": {
            "IS_DARK": True,
            "BG_NEUTRAL": "#070d18",
            "BG_SECONDARY": "#0e1726",
            "CARD_NEUTRAL": "#111c2e",
            "BORDER_NEUTRAL": "#1f324d",
            "TEXT_PRIMARY": "#f0f6fc",
            "TEXT_SECONDARY": "#93a8c7",
            "HEADER_TEXT": "#38bdf8",
            "ACCENT_PURPLE": "#0ea5e9",
            "ACCENT_PURPLE_HOVER": "#38bdf8",
            "ACCENT_PURPLE_PRESSED": "#0284c7",
            "WIDGET_BG": "#0b1320",
            "LIST_ITEM_HOVER": "#1a2a42",
            "HOVER_NEUTRAL": "#1a2a42",
            "CANCEL_BTN_BG": "#162238",
            "CANCEL_BTN_HOVER": "#223554",
            "SHADOW_COLOR": "rgba(14, 165, 233, 0.15)",
            "STATUS_HEADER_BG": "#121e33",
            "SIDEBAR_BG": "#0b1320",
            "SIDEBAR_HOVER_BG": "#17263c",
            "SIDEBAR_COLOR": "#93a8c7",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#f59e0b"
        },
        "light": {
            "IS_DARK": False,
            "BG_NEUTRAL": "#f0f7ff",
            "BG_SECONDARY": "#ffffff",
            "CARD_NEUTRAL": "#ffffff",
            "BORDER_NEUTRAL": "#bae6fd",
            "TEXT_PRIMARY": "#0c4a6e",
            "TEXT_SECONDARY": "#0369a1",
            "HEADER_TEXT": "#0284c7",
            "ACCENT_PURPLE": "#0284c7",
            "ACCENT_PURPLE_HOVER": "#0369a1",
            "ACCENT_PURPLE_PRESSED": "#075985",
            "WIDGET_BG": "#ffffff",
            "LIST_ITEM_HOVER": "#e0f2fe",
            "HOVER_NEUTRAL": "#e0f2fe",
            "CANCEL_BTN_BG": "#e0f2fe",
            "CANCEL_BTN_HOVER": "#bae6fd",
            "SHADOW_COLOR": "rgba(2, 132, 199, 0.12)",
            "STATUS_HEADER_BG": "#e0f2fe",
            "SIDEBAR_BG": "#bae6fd",
            "SIDEBAR_HOVER_BG": "#7dd3fc",
            "SIDEBAR_COLOR": "#0369a1",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#f59e0b"
        }
    },
    "synthwave_magenta": {
        "label": "Synthwave (Obsidian & Magenta)",
        "dark": {
            "IS_DARK": True,
            "BG_NEUTRAL": "#110919",
            "BG_SECONDARY": "#1a0f26",
            "CARD_NEUTRAL": "#221332",
            "BORDER_NEUTRAL": "#441d63",
            "TEXT_PRIMARY": "#fae8ff",
            "TEXT_SECONDARY": "#e879f9",
            "HEADER_TEXT": "#f472b6",
            "ACCENT_PURPLE": "#d946ef",
            "ACCENT_PURPLE_HOVER": "#f472b6",
            "ACCENT_PURPLE_PRESSED": "#c026d3",
            "WIDGET_BG": "#170c22",
            "LIST_ITEM_HOVER": "#351a4d",
            "HOVER_NEUTRAL": "#351a4d",
            "CANCEL_BTN_BG": "#2c1540",
            "CANCEL_BTN_HOVER": "#422060",
            "SHADOW_COLOR": "rgba(217, 70, 239, 0.2)",
            "STATUS_HEADER_BG": "#261338",
            "SIDEBAR_BG": "#170c22",
            "SIDEBAR_HOVER_BG": "#301546",
            "SIDEBAR_COLOR": "#e879f9",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#fbbf24"
        },
        "light": {
            "IS_DARK": False,
            "BG_NEUTRAL": "#fdf4ff",
            "BG_SECONDARY": "#ffffff",
            "CARD_NEUTRAL": "#ffffff",
            "BORDER_NEUTRAL": "#f5d0fe",
            "TEXT_PRIMARY": "#701a75",
            "TEXT_SECONDARY": "#86198f",
            "HEADER_TEXT": "#a21caf",
            "ACCENT_PURPLE": "#c026d3",
            "ACCENT_PURPLE_HOVER": "#a21caf",
            "ACCENT_PURPLE_PRESSED": "#86198f",
            "WIDGET_BG": "#ffffff",
            "LIST_ITEM_HOVER": "#fae8ff",
            "HOVER_NEUTRAL": "#fae8ff",
            "CANCEL_BTN_BG": "#fae8ff",
            "CANCEL_BTN_HOVER": "#f5d0fe",
            "SHADOW_COLOR": "rgba(192, 38, 211, 0.12)",
            "STATUS_HEADER_BG": "#fae8ff",
            "SIDEBAR_BG": "#f5d0fe",
            "SIDEBAR_HOVER_BG": "#f0abfc",
            "SIDEBAR_COLOR": "#86198f",
            "SUCCESS_GREEN": "#10b981",
            "DANGER_RED": "#ef4444",
            "WARNING_AMBER": "#f59e0b"
        }
    }
}


PALETTE_LABELS = {k: v["label"] for k, v in PALETTES.items()}

def get_colors(theme_override: str = None, palette_override: str = None) -> dict:
    theme = theme_override
    palette = palette_override
    if not theme or not palette:
        from utils.config_loader import get_config
        try:
            config = get_config()
            if not theme:
                theme = config.get("behavior.theme", "light")
            if not palette:
                palette = config.get("behavior.color_palette", "iron_ember")
        except Exception:
            if not theme:
                theme = "light"
            if not palette:
                palette = "iron_ember"

    if theme == "system":
        is_dark = is_system_dark_mode()
    elif theme == "dark":
        is_dark = True
    else:
        is_dark = False

    if palette not in PALETTES:
        palette = "iron_ember"

    mode_key = "dark" if is_dark else "light"
    return PALETTES[palette][mode_key]

def refresh_theme_colors(theme_override: str = None, palette_override: str = None):
    global BG_NEUTRAL, CARD_NEUTRAL, BORDER_NEUTRAL, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT_PURPLE, ACCENT_PURPLE_HOVER, ACCENT_PURPLE_PRESSED
    c = get_colors(theme_override, palette_override)
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
    sidebar_bg = c.get("SIDEBAR_BG", "#191510" if is_dark else "#f3e7da")
    sidebar_color = c.get("SIDEBAR_COLOR", "#d9d2c7" if is_dark else "#6b5b4a")
    sidebar_hover_bg = c.get("SIDEBAR_HOVER_BG", "#332c22" if is_dark else "#e8d5bf")
    
    return f"""
        QListWidget#sidebar {{
            background-color: {sidebar_bg};
            border: none;
            border-bottom-left-radius: 20px;
            border-right: 1px solid {c["BORDER_NEUTRAL"]};
            padding-top: 12px;
            color: {sidebar_color};
            font-size: 13px;
            font-weight: 500;
            outline: none;
        }}
        QListWidget#sidebar::item {{
            padding: 10px 16px;
            border-radius: 12px;
            margin: 4px 10px;
            color: {sidebar_color};
            border: 1px solid transparent;
        }}
        QListWidget#sidebar::item:hover {{
            background-color: {sidebar_hover_bg};
            color: {c["TEXT_PRIMARY"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
        }}
        QListWidget#sidebar::item:selected {{
            background-color: {c["ACCENT_PURPLE"]};
            color: #ffffff;
            font-weight: bold;
            border: 1px solid {c["ACCENT_PURPLE_HOVER"]};
        }}
        QPushButton#removeBtn {{
            background-color: transparent;
            color: #ef4444;
            border: 1px solid #ef4444;
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: bold;
        }}
        QPushButton#removeBtn:hover {{
            background-color: #ef4444;
            color: white;
        }}
    """

def get_theme_qss(theme_override: str = None, palette_override: str = None) -> str:
    refresh_theme_colors(theme_override, palette_override)
    c = get_colors(theme_override, palette_override)
    
    return f"""
        /* ─── Global Foundation ─── */
        QDialog, QMainWindow {{
            background-color: {c["BG_NEUTRAL"]};
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}

        /* ─── Premium Scrollbar ─── */
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 4px 1px 4px 1px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background-color: {c["BORDER_NEUTRAL"]};
            min-height: 32px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {c["ACCENT_PURPLE"]};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
            background: none;
            border: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 8px;
            margin: 1px 4px 1px 4px;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {c["BORDER_NEUTRAL"]};
            min-width: 32px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {c["ACCENT_PURPLE"]};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
            background: none;
            border: none;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
        QLabel {{
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
        }}
        QLabel[secondary="true"] {{
            color: {c["TEXT_SECONDARY"]};
        }}
        /* ─── Input Fields with Glow Focus ─── */
        QLineEdit {{
            background-color: {c["WIDGET_BG"]};
            border: 1.5px solid {c["BORDER_NEUTRAL"]};
            border-radius: 10px;
            padding: 10px 14px;
            color: {c["TEXT_PRIMARY"]};
            font-size: 13px;
            font-family: {FONT_FAMILY};
        }}
        QLineEdit:hover {{
            border: 1.5px solid {c["TEXT_SECONDARY"]};
        }}
        QLineEdit:focus {{
            border: 2px solid {c["ACCENT_PURPLE"]};
        }}
        /* ─── Premium Buttons ─── */
        QPushButton {{
            background-color: {c["ACCENT_PURPLE"]};
            color: #ffffff;
            border: none;
            border-radius: 10px;
            padding: 10px 20px;
            font-weight: 600;
            font-size: 13px;
            font-family: {FONT_FAMILY};
        }}
        QPushButton:hover {{
            background-color: {c["ACCENT_PURPLE_HOVER"]};
        }}
        QPushButton:pressed {{
            background-color: {c["ACCENT_PURPLE_PRESSED"]};
        }}

        QPushButton#macCloseBtn {{
            background-color: #ff5f56 !important;
            border-radius: 6px !important;
            border: none !important;
            min-width: 12px !important;
            max-width: 12px !important;
            min-height: 12px !important;
            max-height: 12px !important;
            padding: 0px !important;
        }}
        QPushButton#macCloseBtn:hover {{
            background-color: #ff4c40 !important;
        }}
        QPushButton#macMinBtn {{
            background-color: #ffbd2e !important;
            border-radius: 6px !important;
            border: none !important;
            min-width: 12px !important;
            max-width: 12px !important;
            min-height: 12px !important;
            max-height: 12px !important;
            padding: 0px !important;
        }}
        QPushButton#macMinBtn:hover {{
            background-color: #ffb114 !important;
        }}
        QPushButton#macMaxBtn {{
            background-color: #27c93f !important;
            border-radius: 6px !important;
            border: none !important;
            min-width: 12px !important;
            max-width: 12px !important;
            min-height: 12px !important;
            max-height: 12px !important;
            padding: 0px !important;
        }}
        QPushButton#macMaxBtn:hover {{
            background-color: #1ec030 !important;
        }}
        QPushButton#cancelBtn, QPushButton#changePwdBtn, QPushButton#testFaceBtn {{
            background-color: {c["CANCEL_BTN_BG"]};
            color: {c["TEXT_PRIMARY"]};
            border: 1.5px solid {c["BORDER_NEUTRAL"]};
            border-radius: 8px;
            padding: 10px 20px;
            font-weight: 600;
            font-size: 13px;
        }}
        QPushButton#cancelBtn:hover, QPushButton#changePwdBtn:hover, QPushButton#testFaceBtn:hover {{
            background-color: {c["CANCEL_BTN_HOVER"]};
            border-color: {c["TEXT_SECONDARY"]};
        }}
        QPushButton#removeSelectedBtn, QPushButton#clearIntrudersBtn {{
            background-color: #ef4444;
            color: #ffffff;
            border: none;
            font-weight: 600;
            border-radius: 8px;
            padding: 10px 20px;
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
            border-radius: 8px;
            padding: 10px 20px;
            font-weight: 600;
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
            border-radius: 10px;
            color: {c["TEXT_PRIMARY"]};
            font-size: 13px;
            font-family: {FONT_FAMILY};
            padding: 6px;
            outline: none;
        }}
        QListWidget::item {{
            padding: 10px 12px;
            border-radius: 6px;
            color: {c["TEXT_PRIMARY"]};
            margin: 1px 2px;
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
        QHeaderView {{
            background-color: {c["CANCEL_BTN_BG"]};
            border: none;
            outline: none;
        }}
        QHeaderView::section, QHeaderView::section:horizontal {{
            background-color: {c["CANCEL_BTN_BG"]};
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-weight: 600;
            font-size: 13px;
            padding: 8px 12px;
            min-height: 28px;
            border: none;
            border-bottom: 2px solid {c["BORDER_NEUTRAL"]};
            outline: none;
        }}
        QComboBox {{
            background-color: {c["WIDGET_BG"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 6px;
            padding: 6px 32px 6px 12px;
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-size: 13px;
            min-height: 24px;
        }}
        QComboBox:focus, QComboBox:hover {{
            border: 1px solid {c["ACCENT_PURPLE"]};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 28px;
            border: none;
            background: transparent;
        }}
        QComboBox::down-arrow {{
            width: 0px;
            height: 0px;
            border: none;
            background: transparent;
            image: none;
        }}
        QComboBoxPrivateContainer {{
            background: transparent;
            border: none;
        }}
        QComboBox QAbstractItemView, QComboBox QAbstractItemView::viewport, QComboBox QAbstractItemView QWidget#qt_scrollarea_viewport {{
            background-color: {c["CARD_NEUTRAL"]} !important;
            border: 1.5px solid {c["BORDER_NEUTRAL"]};
            color: {c["TEXT_PRIMARY"]};
            selection-background-color: {c["ACCENT_PURPLE"]};
            selection-color: #ffffff;
            outline: none;
            padding: 4px;
            border-radius: 10px;
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
        QSpinBox, QDoubleSpinBox {{
            background-color: {c["WIDGET_BG"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 6px;
            padding: 6px 28px 6px 12px;
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-size: 13px;
            min-height: 24px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus, QSpinBox:hover, QDoubleSpinBox:hover {{
            border: 1px solid {c["ACCENT_PURPLE"]};
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 20px;
            height: 12px;
            border: none;
            background: transparent;
            margin-right: 4px;
            margin-top: 2px;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 20px;
            height: 12px;
            border: none;
            background: transparent;
            margin-right: 4px;
            margin-bottom: 2px;
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            width: 0;
            height: 0;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-bottom: 4px solid {c["TEXT_PRIMARY"]};
        }}
        QSpinBox::up-button:hover QSpinBox::up-arrow, QDoubleSpinBox::up-button:hover QDoubleSpinBox::up-arrow {{
            border-bottom-color: {c["ACCENT_PURPLE"]};
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            width: 0;
            height: 0;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-top: 4px solid {c["TEXT_PRIMARY"]};
        }}
        QSpinBox::down-button:hover QSpinBox::down-arrow, QDoubleSpinBox::down-button:hover QDoubleSpinBox::down-arrow {{
            border-top-color: {c["ACCENT_PURPLE"]};
        }}
        QCheckBox {{
            spacing: 10px;
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1.5px solid {c["BORDER_NEUTRAL"]};
            background-color: {c["WIDGET_BG"]};
        }}
        QCheckBox::indicator:hover {{
            border-color: {c["ACCENT_PURPLE"]};
        }}
        QCheckBox::indicator:checked {{
            background-color: {c["ACCENT_PURPLE"]};
            border-color: {c["ACCENT_PURPLE"]};
            image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'%3E%3C/polyline%3E%3C/svg%3E");
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
        QHeaderView {{
            background-color: {c["CANCEL_BTN_BG"]};
            border: none;
            outline: none;
        }}
        QHeaderView::section, QHeaderView::section:horizontal {{
            background-color: {c["CANCEL_BTN_BG"]};
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-weight: 600;
            font-size: 13px;
            padding: 8px 12px;
            min-height: 28px;
            border: none;
            border-bottom: 2px solid {c["BORDER_NEUTRAL"]};
            outline: none;
        }}
        QTableWidget::item {{
            padding: 6px;
            color: {c["TEXT_PRIMARY"]};
        }}
        QScrollArea, QScrollArea > QWidget#qt_scrollarea_viewport {{
            background-color: transparent;
            border: none;
        }}
        QStackedWidget, QStackedWidget > QWidget {{
            background-color: transparent;
        }}
        QPushButton#removeBtn {{
            background-color: transparent;
            color: #ef4444;
            border: 1.5px solid #ef4444;
            border-radius: 6px;
            padding: 5px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
        QPushButton#removeBtn:hover {{
            background-color: #ef4444;
            color: white;
        }}
        /* ─── Text Edit ─── */
        QTextEdit {{
            background-color: {c["WIDGET_BG"]};
            border: 1.5px solid {c["BORDER_NEUTRAL"]};
            border-radius: 8px;
            padding: 8px;
            color: {c["TEXT_PRIMARY"]};
            font-family: {FONT_FAMILY};
            font-size: 13px;
        }}
        QTextEdit:focus {{
            border: 2px solid {c["ACCENT_PURPLE"]};
        }}
        /* ─── Tooltips ─── */
        QToolTip {{
            background-color: {c["CARD_NEUTRAL"]};
            color: {c["TEXT_PRIMARY"]};
            border: 1px solid {c["BORDER_NEUTRAL"]};
            border-radius: 6px;
            padding: 6px 10px;
            font-family: {FONT_FAMILY};
            font-size: 12px;
        }}
    """

def get_card_qss(importance: str = "normal", colors: dict = None) -> str:
    if colors is None:
        colors = get_colors()
    card_bg = colors["CARD_NEUTRAL"]
    border_color = colors["BORDER_NEUTRAL"]
    text_color = colors["TEXT_PRIMARY"]
    text_sec = colors["TEXT_SECONDARY"]
    header_color = colors.get("HEADER_TEXT", "#fb923c")
    accent = colors["ACCENT_PURPLE"]
    accent_hover = colors.get("ACCENT_PURPLE_HOVER", "#9a3412")
    danger = colors.get("DANGER_RED", "#ef4444")
    widget_bg = colors.get("WIDGET_BG", "#191510")
    cancel_bg = colors.get("CANCEL_BTN_BG", "#f5f4f0")
    cancel_hover = colors.get("CANCEL_BTN_HOVER", "#e5ddd0")
    
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
            border-radius: 14px;
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
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background-color: {widget_bg};
            border: 1px solid {border_color};
            border-radius: 10px;
            padding: 6px 32px 6px 12px;
            color: {text_color};
            font-size: 13px;
            min-height: 24px;
        }}

        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QComboBox:hover {{
            border: 1px solid {accent};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 28px;
            border: none;
            background: transparent;
        }}
        QComboBox::down-arrow {{
            width: 0px;
            height: 0px;
            border: none;
            background: transparent;
            image: none;
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 20px;
            height: 12px;
            border: none;
            background: transparent;
            margin-right: 4px;
            margin-top: 2px;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 20px;
            height: 12px;
            border: none;
            background: transparent;
            margin-right: 4px;
            margin-bottom: 2px;
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            width: 0;
            height: 0;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-bottom: 4px solid {text_color};
        }}
        QSpinBox::up-button:hover QSpinBox::up-arrow, QDoubleSpinBox::up-button:hover QDoubleSpinBox::up-arrow {{
            border-bottom-color: {accent};
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            width: 0;
            height: 0;
            border-left: 3px solid transparent;
            border-right: 3px solid transparent;
            border-top: 4px solid {text_color};
        }}
        QSpinBox::down-button:hover QSpinBox::down-arrow, QDoubleSpinBox::down-button:hover QDoubleSpinBox::down-arrow {{
            border-top-color: {accent};
        }}
        QCheckBox {{
            spacing: 10px;
            color: {text_color};
            font-size: 13px;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1.5px solid {border_color};
            background-color: {widget_bg};
        }}
        QCheckBox::indicator:hover {{
            border-color: {accent};
        }}
        QCheckBox::indicator:checked {{
            background-color: {accent};
            border-color: {accent};
            image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'%3E%3C/polyline%3E%3C/svg%3E");
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
    pixmap = app_icon.pixmap(24, 24).copy()
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

class AnimatedSpinBox(QWidget):
    """
    A modern, animated numerical input widget with smooth [-] and [+] spring-bounce buttons
    and a clean center value display with micro-animations.
    """
    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = 0
        self._max = 999999
        self._value = 0
        self._step = 1

        self.setFixedHeight(34)
        self.setFixedWidth(136)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.dec_btn = AnimatedButton("-", self)
        self.dec_btn.setFixedSize(32, 32)
        self.dec_btn.setObjectName("spinDecBtn")
        self.dec_btn.clicked.connect(self._decrement)

        self.input_edit = QLineEdit(str(self._value), self)
        self.input_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_edit.setFixedSize(60, 32)
        self.input_edit.editingFinished.connect(self._on_edit_finished)

        self.inc_btn = AnimatedButton("+", self)
        self.inc_btn.setFixedSize(32, 32)
        self.inc_btn.setObjectName("spinIncBtn")
        self.inc_btn.clicked.connect(self._increment)

        layout.addWidget(self.dec_btn)
        layout.addWidget(self.input_edit)
        layout.addWidget(self.inc_btn)
        self._apply_style()

    def _apply_style(self, theme_mode=None, palette_val=None):
        from ui.theme import get_colors, FONT_FAMILY
        c = get_colors(theme_mode, palette_val)
        bg = c.get("CARD_NEUTRAL", "#ffffff")
        btn_bg = c.get("CANCEL_BTN_BG", "#e6f7ed")
        btn_hover = c.get("CANCEL_BTN_HOVER", "#d1fae5")
        text = c.get("TEXT_PRIMARY", "#064e3b")
        border = c.get("BORDER_NEUTRAL", "#d1fae5")
        accent = c.get("ACCENT_PURPLE", "#059669")

        self.dec_btn.setStyleSheet(f"""
            QPushButton#spinDecBtn {{
                background-color: {btn_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                font-weight: bold;
                font-size: 15px;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton#spinDecBtn:hover {{
                background-color: {btn_hover};
                border-color: {accent};
                color: {accent};
            }}
        """)
        self.inc_btn.setStyleSheet(f"""
            QPushButton#spinIncBtn {{
                background-color: {btn_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                font-weight: bold;
                font-size: 15px;
                padding: 0px;
                margin: 0px;
            }}
            QPushButton#spinIncBtn:hover {{
                background-color: {btn_hover};
                border-color: {accent};
                color: {accent};
            }}
        """)
        self.input_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {bg};
                color: {text};
                border: 1.5px solid {border};
                border-radius: 8px;
                font-family: {FONT_FAMILY};
                font-size: 14px;
                font-weight: bold;
                padding: 0px 4px;
                margin: 0px;
            }}
            QLineEdit:focus {{
                border: 2px solid {accent};
            }}
        """)

    def setRange(self, min_val: int, max_val: int):
        self._min = min_val
        self._max = max_val
        self.setValue(self._value)

    def setSingleStep(self, step: int):
        self._step = max(1, step)

    def value(self) -> int:
        return self._value

    def setValue(self, val: int):
        try:
            v = int(val)
        except (ValueError, TypeError):
            v = self._min
        v = max(self._min, min(self._max, v))
        if self._value != v:
            self._value = v
            self.input_edit.setText(str(self._value))
            self.valueChanged.emit(self._value)
        else:
            self.input_edit.setText(str(self._value))

    def _decrement(self):
        self.setValue(self._value - self._step)

    def _increment(self):
        self.setValue(self._value + self._step)

    def _on_edit_finished(self):
        try:
            val = int(self.input_edit.text())
            self.setValue(val)
        except ValueError:
            self.input_edit.setText(str(self._value))

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

        # 1. Fill base item rect with solid card neutral background to eliminate transparency gaps
        bg_card = QColor(c["CARD_NEUTRAL"])
        painter.fillRect(rect, bg_card)

        padded_rect = rect.adjusted(4, 2, -4, -2)

        if is_selected:
            bg_color = QColor(c["ACCENT_PURPLE"])
            text_color = QColor("#ffffff")
        elif is_hovered:
            bg_color = QColor(c["LIST_ITEM_HOVER"])
            text_color = QColor(c["TEXT_PRIMARY"])
        else:
            bg_color = bg_card
            text_color = QColor(c["TEXT_PRIMARY"])

        # Draw rounded rectangle background for ALL items (selected, hovered, and unselected)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(padded_rect, 6, 6)

        # 2. Draw decoration icon if present
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        has_icon = False
        if icon:
            if isinstance(icon, QIcon) and not icon.isNull():
                icon_size = option.decorationSize if (hasattr(option, "decorationSize") and option.decorationSize.isValid()) else QSize(18, 18)
                icon_rect = QRect(padded_rect.x() + 10, int(padded_rect.center().y() - icon_size.height() / 2), icon_size.width(), icon_size.height())
                icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)
                has_icon = True
            elif isinstance(icon, QPixmap) and not icon.isNull():
                pm_rect = QRect(padded_rect.x() + 10, int(padded_rect.center().y() - 9), 18, 18)
                painter.drawPixmap(pm_rect, icon)
                has_icon = True

        left_offset = 36 if has_icon else 12
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        painter.setFont(option.font)
        painter.setPen(text_color)
        text_rect = padded_rect.adjusted(left_offset, 0, -32, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        if is_selected:
            chk_color = QColor("#ffffff")
            painter.setPen(QPen(chk_color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            chk_x = padded_rect.right() - 18
            chk_y = padded_rect.center().y()
            path = QPainterPath()
            path.moveTo(chk_x, chk_y - 1)
            path.lineTo(chk_x + 4, chk_y + 4)
            path.lineTo(chk_x + 10, chk_y - 4)
            painter.drawPath(path)

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex):
        size = super().sizeHint(option, index)
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(option.font)
        text_w = fm.horizontalAdvance(text) + (80 if index.data(Qt.ItemDataRole.DecorationRole) else 60)
        size.setWidth(max(size.width(), text_w))
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
        self._apply_view_style()

    def _apply_view_style(self):
        from ui.theme import get_colors
        c = get_colors()
        view = self.view()
        if view:
            container = view.parentWidget()
            if container:
                container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                container.setStyleSheet("background: transparent; border: none; padding: 2px;")
            
            view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            view.setAutoFillBackground(True)
            
            vp = view.viewport()
            if vp:
                vp.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
                vp.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
                vp.setAutoFillBackground(True)
                vp.setStyleSheet(f"background-color: {c['CARD_NEUTRAL']} !important;")
            
            view.setStyleSheet(f"""
                QListView, QListView::viewport {{
                    background-color: {c["CARD_NEUTRAL"]} !important;
                    color: {c["TEXT_PRIMARY"]};
                }}
                QListView {{
                    border: 1.5px solid {c["BORDER_NEUTRAL"]};
                    border-radius: 10px;
                    padding: 4px;
                    outline: none;
                }}
                QListView::item {{
                    background-color: {c["CARD_NEUTRAL"]};
                    color: {c["TEXT_PRIMARY"]};
                    padding: 8px 12px;
                    border-radius: 6px;
                }}
            """)

    @Property(float)
    def arrow_rotation(self):
        return self._arrow_rotation

    @arrow_rotation.setter
    def arrow_rotation(self, val):
        self._arrow_rotation = val
        self.update()

    def showPopup(self):
        self._apply_view_style()
        view = self.view()
        if view and view.parentWidget():
            container = view.parentWidget()
            container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            container.setStyleSheet("background: transparent; border: none;")
        if self.anim:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"arrow_rotation")
        self.anim.setDuration(220)
        self.anim.setStartValue(self._arrow_rotation)
        self.anim.setEndValue(180.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

        # Ensure popup view is wide enough so item text is never truncated
        view = self.view()
        fm = self.fontMetrics()
        max_w = self.width()
        for i in range(self.count()):
            w = fm.horizontalAdvance(self.itemText(i)) + 64
            if w > max_w:
                max_w = w
        view.setMinimumWidth(max_w)
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
        bg_active = QColor(c.get("ACCENT_PURPLE", "#c2410c"))
        
        border_inactive = QColor(c.get("BORDER_NEUTRAL", "#d9d2c7"))
        border_active = QColor(c.get("ACCENT_PURPLE", "#c2410c"))

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
    def __init__(self, parent, title="", allow_maximize=True, allow_minimize=True, show_theme_toggle=False):
        super().__init__(parent)
        self.parent = parent
        self.allow_maximize = allow_maximize
        self.allow_minimize = allow_minimize
        self.show_theme_toggle = show_theme_toggle
        self.setFixedHeight(42)
        
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
        
        # Optional Theme Toggle
        if self.show_theme_toggle:
            self.theme_toggle = SlidingThemeToggle(self)
            self.theme_toggle.toggled.connect(self.on_theme_toggled)
            layout.addWidget(self.theme_toggle)
            layout.addSpacing(8)
        else:
            self.theme_toggle = None

        # 2. Traffic Light Buttons (Right side)
        # Minimize (Yellow)
        self.min_btn = QPushButton()
        self.min_btn.setObjectName("macMinBtn")
        self.min_btn.setFixedSize(12, 12)
        self.min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_btn.setToolTip("Minimize")
        self.min_btn.setStyleSheet("""
            QPushButton#macMinBtn {
                background-color: #ffbd2e;
                border-radius: 6px;
                border: none;
            }
            QPushButton#macMinBtn:hover {
                background-color: #ffaa00;
            }
        """)
        if self.allow_minimize:
            self.min_btn.clicked.connect(self.parent.showMinimized)
        else:
            self.min_btn.setEnabled(False)
            self.min_btn.hide()
        
        # Maximize (Green)
        self.max_btn = QPushButton()
        self.max_btn.setObjectName("macMaxBtn")
        self.max_btn.setFixedSize(12, 12)
        self.max_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.max_btn.setToolTip("Maximize")
        self.max_btn.setStyleSheet("""
            QPushButton#macMaxBtn {
                background-color: #27c93f;
                border-radius: 6px;
                border: none;
            }
            QPushButton#macMaxBtn:hover {
                background-color: #1eb336;
            }
        """)
        if self.allow_maximize:
            self.max_btn.clicked.connect(self.toggle_maximize)
        else:
            self.max_btn.setEnabled(False)
            self.max_btn.hide()
            
        # Close (Red)
        self.close_btn = QPushButton()
        self.close_btn.setObjectName("macCloseBtn")
        self.close_btn.setFixedSize(12, 12)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Close")
        self.close_btn.setStyleSheet("""
            QPushButton#macCloseBtn {
                background-color: #ff5f56;
                border-radius: 6px;
                border: none;
            }
            QPushButton#macCloseBtn:hover {
                background-color: #e84136;
            }
        """)
        self.close_btn.clicked.connect(self.parent.close)
             
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)
        
        self.drag_position = QPoint()
        self.apply_theme_dynamically()

        
    def apply_theme_dynamically(self):
        from ui.theme import get_colors, FONT_FAMILY
        theme_mode = getattr(self.parent, "theme_mode", None)
        c = get_colors(theme_mode)
        self.title_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {c['TEXT_PRIMARY']}; font-family: {FONT_FAMILY}; padding: 0px; background: transparent;")

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
        
        from ui.theme import get_colors
        c_light = get_colors("light")
        c_dark = get_colors("dark")
        
        accent_light = QColor(c_light.get("ACCENT_PURPLE", "#c2410c"))
        accent_dark = QColor(c_dark.get("ACCENT_PURPLE", "#f97316"))
        
        r = int(accent_light.red() + (accent_dark.red() - accent_light.red()) * self._knob_position)
        g = int(accent_light.green() + (accent_dark.green() - accent_light.green()) * self._knob_position)
        b = int(accent_light.blue() + (accent_dark.blue() - accent_light.blue()) * self._knob_position)
        active_color = QColor(r, g, b)
        
        inactive_color = QColor(c_light.get("BORDER_NEUTRAL", "#d9d2c7"))
        track_color = active_color if self._knob_position > 0.5 else inactive_color
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


from PySide6.QtCore import QObject, QEvent, QRect, QPoint

class WindowDragResizeFilter(QObject):
    """
    Event filter providing smooth mouse edge/corner resizing and titlebar moving
    for frameless translucent windows with rounded corners.
    """
    EDGE_MARGIN = 8

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.window = window
        self.resizing = False
        self.resize_edges = ""
        self.drag_start_pos = QPoint()
        self.window_start_geo = QRect()
        self.window.setMouseTracking(True)
        if hasattr(self.window, "main_container") and self.window.main_container:
            self.window.main_container.setMouseTracking(True)
            self.window.main_container.installEventFilter(self)
        self.window.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseMove:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            if self.resizing:
                self._handle_resize(event.globalPosition().toPoint())
                return True
            else:
                edges = self._get_edges(pos)
                self._update_cursor(edges)
                return False

        elif event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                edges = self._get_edges(pos)
                if edges:
                    self.resizing = True
                    self.resize_edges = edges
                    self.drag_start_pos = event.globalPosition().toPoint()
                    self.window_start_geo = self.window.geometry()
                    return True

        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self.resizing:
                self.resizing = False
                self.window.unsetCursor()
                return True

        return super().eventFilter(obj, event)

    def _get_edges(self, pos: QPoint) -> str:
        rect = self.window.rect()
        top = pos.y() <= self.EDGE_MARGIN
        bottom = pos.y() >= rect.height() - self.EDGE_MARGIN
        left = pos.x() <= self.EDGE_MARGIN
        right = pos.x() >= rect.width() - self.EDGE_MARGIN

        edges = ""
        if top: edges += "T"
        if bottom: edges += "B"
        if left: edges += "L"
        if right: edges += "R"
        return edges

    def _update_cursor(self, edges: str):
        try:
            if edges in ("TL", "BR"):
                self.window.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif edges in ("TR", "BL"):
                self.window.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif "L" in edges or "R" in edges:
                self.window.setCursor(Qt.CursorShape.SizeHorCursor)
            elif "T" in edges or "B" in edges:
                self.window.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                self.window.unsetCursor()
        except Exception:
            pass

    def _handle_resize(self, global_pos: QPoint):
        diff = global_pos - self.drag_start_pos
        geo = QRect(self.window_start_geo)
        min_w = self.window.minimumWidth() or 300
        min_h = self.window.minimumHeight() or 200

        if "R" in self.resize_edges:
            geo.setWidth(max(min_w, self.window_start_geo.width() + diff.x()))
        if "B" in self.resize_edges:
            geo.setHeight(max(min_h, self.window_start_geo.height() + diff.y()))
        if "L" in self.resize_edges:
            new_w = max(min_w, self.window_start_geo.width() - diff.x())
            geo.setLeft(self.window_start_geo.right() - new_w)
        if "T" in self.resize_edges:
            new_h = max(min_h, self.window_start_geo.height() - diff.y())
            geo.setTop(self.window_start_geo.bottom() - new_h)

        self.window.setGeometry(geo)


class PulsingStatusDot(QWidget):
    """
    A smooth pulsing status dot widget that breathes/pulses softly when active or warning.
    """
    def __init__(self, color_hex: str = "#10b981", parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self._color_hex = color_hex
        self._pulse_opacity = 0.4
        
        self.anim = QPropertyAnimation(self, b"pulse_opacity")
        self.anim.setDuration(1200)
        self.anim.setStartValue(0.3)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.anim.setLoopCount(-1)  # Infinite loop breathing
        self.anim.start()

    @Property(float)
    def pulse_opacity(self):
        return self._pulse_opacity

    @pulse_opacity.setter
    def pulse_opacity(self, val):
        self._pulse_opacity = val
        self.update()

    def set_color(self, color_hex: str):
        self._color_hex = color_hex
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        base_color = QColor(self._color_hex)
        
        # Outer glow ring
        glow_color = QColor(base_color)
        glow_color.setAlphaF(self._pulse_opacity * 0.45)
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.PenStyle.NoPen)
        glow_radius = 5.0 + (2.5 * self._pulse_opacity)
        painter.drawEllipse(center, glow_radius, glow_radius)

        # Core dot
        core_color = QColor(base_color)
        core_color.setAlphaF(0.95)
        painter.setBrush(QBrush(core_color))
        painter.drawEllipse(center, 3.5, 3.5)


class AnimatedButton(QPushButton):
    """
    A premium button subclass with smooth hover scaling and spring-click press feedback.
    """
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._scale = 1.0
        self.anim = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @Property(float)
    def button_scale(self):
        return self._scale

    @button_scale.setter
    def button_scale(self, val):
        self._scale = val
        self.update()

    def enterEvent(self, event):
        self._animate_scale(1.025)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_scale(1.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._animate_scale(0.97)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._animate_scale(1.025 if self.underMouse() else 1.0)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        if abs(self._scale - 1.0) < 0.001:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        rect = self.rect()
        cx = rect.width() / 2.0
        cy = rect.height() / 2.0

        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        super().paintEvent(event)
        painter.end()

    def _animate_scale(self, target):
        if self.anim:
            self.anim.stop()
        self.anim = QPropertyAnimation(self, b"button_scale")
        self.anim.setDuration(160)
        self.anim.setStartValue(self._scale)
        self.anim.setEndValue(target)
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack if target > 1.0 else QEasingCurve.Type.OutQuad)
        self.anim.start()

