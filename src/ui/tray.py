from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QPen, QPolygonF
from PySide6.QtCore import Qt, QPointF, QRectF

def create_circle_icon(color_hex: str) -> QIcon:
    """
    Renders a custom circle icon dynamically using QPainter.
    Avoids host icon-theme dependency errors on minimal desktop environments.
    """
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # White border ring
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(3, 3, 18, 18)
    
    # Inner colored status circle
    painter.setBrush(QColor(color_hex))
    painter.drawEllipse(5, 5, 14, 14)
    
    painter.end()
    return QIcon(pixmap)


def create_square_icon(color_hex: str) -> QIcon:
    """Rounded-square variant of the status icon, same visual language as the circle."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(3, 3, 18, 18, 6, 6)

    painter.setBrush(QColor(color_hex))
    painter.drawRoundedRect(5, 5, 14, 14, 4, 4)

    painter.end()
    return QIcon(pixmap)


def create_shield_icon(color_hex: str) -> QIcon:
    """Shield glyph - reads as 'protection/security' at a glance in the tray."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    def shield_path(cx, top, half_w, height):
        return QPolygonF([
            QPointF(cx, top),
            QPointF(cx + half_w, top + half_w * 0.6),
            QPointF(cx + half_w, top + height * 0.55),
            QPointF(cx, top + height),
            QPointF(cx - half_w, top + height * 0.55),
            QPointF(cx - half_w, top + half_w * 0.6),
        ])

    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPolygon(shield_path(12, 2, 9, 20))

    painter.setBrush(QColor(color_hex))
    painter.drawPolygon(shield_path(12, 4, 6.5, 15))

    painter.end()
    return QIcon(pixmap)


def create_lock_icon(color_hex: str) -> QIcon:
    """Padlock glyph - the most literal option for a lock/access-control app."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # White backing plate so the glyph stays legible on any panel background/theme
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 20, 20, 5, 5)

    # Shackle
    pen = QPen(QColor(color_hex))
    pen.setWidth(2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(8, 5, 8, 9), 0, 180 * 16)

    # Body
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color_hex))
    painter.drawRoundedRect(6, 11, 12, 9, 2, 2)

    painter.end()
    return QIcon(pixmap)


def create_gate_icon(color_hex: str) -> QIcon:
    """Vertical-bar 'gate' glyph, a nod to the FaceGATE name specifically."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 20, 20, 5, 5)

    painter.setBrush(QColor(color_hex))
    bar_w = 3
    for x in (5, 10.5, 16):
        painter.drawRoundedRect(QRectF(x, 5, bar_w, 14), 1.5, 1.5)

    painter.end()
    return QIcon(pixmap)


# Registry of selectable tray icon styles. Keys are the values stored in
# config ("behavior.tray_icon_style"); "circle" remains the default so
# existing installs/configs are unaffected. Adding a new style only
# requires a new renderer function and one line here.
TRAY_ICON_STYLES = {
    "circle": create_circle_icon,
    "square": create_square_icon,
    "shield": create_shield_icon,
    "lock": create_lock_icon,
    "gate": create_gate_icon,
}
TRAY_ICON_STYLE_LABELS = {
    "circle": "Circle (Default)",
    "square": "Square",
    "shield": "Shield",
    "lock": "Padlock",
    "gate": "Gate Bars",
}


def get_tray_icon_renderer(style_name: str):
    """Looks up a renderer by name, falling back to the default circle style
    for unknown/missing values so a bad config can never crash icon creation."""
    return TRAY_ICON_STYLES.get(style_name, create_circle_icon)


def get_configured_tray_icon_renderer():
    """Reads behavior.tray_icon_style from config and returns the matching
    renderer, defaulting to the circle style if unset, invalid, or if config
    can't be loaded for any reason (e.g. during early startup)."""
    try:
        from utils.config_loader import get_config
        style_name = get_config().get("behavior.tray_icon_style", "circle")
    except Exception:
        style_name = "circle"
    return get_tray_icon_renderer(style_name)

class FaceGateTray(QSystemTrayIcon):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        
        from ui.theme import ACCENT_PURPLE, TEXT_SECONDARY
        self._accent_color = ACCENT_PURPLE
        self._inactive_color = TEXT_SECONDARY
        # Pre-render state icons using the user's chosen preset (defaults to
        # "circle", so existing installs/configs see no visual change).
        self._render_icons()
        
        self.setIcon(self.active_icon)
        self.setToolTip("FaceGate-Linux")
        
        # Setup context menu
        self.menu = QMenu()
        # Connect aboutToShow to dynamically rebuild menu options
        self.menu.aboutToShow.connect(self.rebuild_menu)
        self.setContextMenu(self.menu)
        
        self.rebuild_menu()

    def _render_icons(self):
        """(Re)renders active/inactive tray icons using the currently configured style."""
        renderer = get_configured_tray_icon_renderer()
        self.active_icon = renderer(self._accent_color)
        self.inactive_icon = renderer(self._inactive_color)

    def refresh_icon_style(self):
        """Re-renders tray icons after a config change (e.g. the user picked a
        different tray icon style in Settings) and applies the correct one for
        the current active/inactive state. Safe to call at any time."""
        try:
            self._render_icons()
            self.update_tray_state()
        except Exception as e:
            import logging
            logging.warning(f"Error refreshing tray icon style: {e}")

    def update_tray_state(self):
        """Updates the tray icon image depending on active status."""
        if self.main_app.is_active():
            self.setIcon(self.active_icon)
        else:
            self.setIcon(self.inactive_icon)

    def rebuild_menu(self):
        """Dynamically rebuilds the menu items to reflect live state."""
        self.menu.clear()
        
        # Status header
        is_active = self.main_app.is_active()
        status_text = "Active" if is_active else "Inactive"
        if self.main_app.disabled_until:
            remaining = int(self.main_app.get_remaining_disabled_seconds())
            if remaining > 0:
                mins, secs = divmod(remaining, 60)
                status_text = f"Inactive (Paused: {mins:02d}:{secs:02d})"
                
        status_action = QAction(status_text, self.menu)
        status_action.setEnabled(False)
        status_action.setIcon(self.active_icon if is_active else self.inactive_icon)
        self.menu.addAction(status_action)
        self.menu.addSeparator()
        
        # Protected apps rows
        protected_apps = self.main_app.get_protected_apps()
        tray_apps = [app for app in protected_apps if app.get("show_in_tray", True)][:5]
        from ui.theme import resolve_app_icon, composite_tray_icon
        for app in tray_apps:
            app_id = app.get("id")
            app_name = app.get("name", app_id)
            desktop_name = app.get("desktop_name")
            
            is_authed = self.main_app.is_app_authorized(app_id)
            display_text = app_name
            
            # Resolve real icon and composite overlay badge
            base_icon = resolve_app_icon(app.get("icon", ""))
            composited_icon = composite_tray_icon(base_icon, is_locked=not is_authed)
            
            app_action = QAction(display_text, self.menu)
            app_action.setIcon(composited_icon)
            
            # Action triggers
            if not is_authed:
                def make_trigger(d_name=desktop_name):
                    return lambda: self.main_app.trigger_manual_auth(d_name)
                app_action.triggered.connect(make_trigger())
            else:
                def make_relock(a_id=app_id):
                    return lambda: self.main_app.relock_app(a_id)
                app_action.triggered.connect(make_relock())
                
            self.menu.addAction(app_action)
            
        self.menu.addSeparator()
        
        # Re-lock All
        relock_all_action = QAction("Re-lock All Apps", self.menu)
        relock_all_action.triggered.connect(self.main_app.relock_all)
        has_unlocked = any(self.main_app.is_app_authorized(app["id"]) for app in protected_apps)
        relock_all_action.setEnabled(is_active and has_unlocked)
        self.menu.addAction(relock_all_action)
        
        # Disable FaceGate submenu
        disable_menu = self.menu.addMenu("Disable FaceGate")
        disable_menu.setEnabled(is_active)
        for mins in [5, 15, 30, 60]:
            disable_action = QAction(f"For {mins} minutes", self.menu)
            def make_disable(m=mins):
                return lambda: self.main_app.disable_for(m)
            disable_action.triggered.connect(make_disable())
            disable_menu.addAction(disable_action)
            
        # Enable option if inactive
        if not is_active:
            resume_action = QAction("Enable FaceGate", self.menu)
            resume_action.triggered.connect(self.main_app.resume)
            self.menu.addAction(resume_action)
            
        self.menu.addSeparator()
        
        # Settings
        settings_action = QAction("Settings...", self.menu)
        settings_action.triggered.connect(self.main_app.open_settings)
        self.menu.addAction(settings_action)

        # Enroll Face
        enroll_action = QAction("Enroll Face...", self.menu)
        enroll_action.triggered.connect(self.main_app.open_enrollment)
        self.menu.addAction(enroll_action)
        
        self.menu.addSeparator()
        
        # Quit
        quit_action = QAction("Quit FaceGate", self.menu)
        quit_action.triggered.connect(self.main_app.quit_app)
        self.menu.addAction(quit_action)
