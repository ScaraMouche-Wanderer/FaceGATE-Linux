from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QPen, QPolygonF
from PySide6.QtCore import Qt, QPointF, QRectF

def create_circle_icon(color_hex: str) -> QIcon:
    """
    Renders a custom circle icon dynamically using QPainter at 48x48 HiDPI.
    Avoids host icon-theme dependency errors on minimal desktop environments.
    """
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # White border ring
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(6, 6, 36, 36)
    
    # Inner colored status circle
    painter.setBrush(QColor(color_hex))
    painter.drawEllipse(10, 10, 28, 28)
    
    painter.end()
    return QIcon(pixmap)


def create_square_icon(color_hex: str) -> QIcon:
    """Rounded-square variant of the status icon at 48x48 HiDPI."""
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(6, 6, 36, 36, 12, 12)

    painter.setBrush(QColor(color_hex))
    painter.drawRoundedRect(10, 10, 28, 28, 8, 8)

    painter.end()
    return QIcon(pixmap)


def create_shield_icon(color_hex: str) -> QIcon:
    """Shield glyph at 48x48 HiDPI - reads as 'protection/security' at a glance."""
    pixmap = QPixmap(48, 48)
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
    painter.drawPolygon(shield_path(24, 4, 18, 40))

    painter.setBrush(QColor(color_hex))
    painter.drawPolygon(shield_path(24, 8, 13, 30))

    painter.end()
    return QIcon(pixmap)


def create_lock_icon(color_hex: str) -> QIcon:
    """Padlock glyph at 48x48 HiDPI - lock/access-control icon."""
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # White backing plate
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 40, 40, 10, 10)

    # Shackle
    pen = QPen(QColor(color_hex))
    pen.setWidth(4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(16, 10, 16, 18), 0, 180 * 16)

    # Body
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color_hex))
    painter.drawRoundedRect(12, 22, 24, 18, 4, 4)

    painter.end()
    return QIcon(pixmap)


def create_gate_icon(color_hex: str) -> QIcon:
    """Vertical-bar 'gate' glyph at 48x48 HiDPI."""
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    painter.setBrush(QColor("#ffffff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 4, 40, 40, 10, 10)

    painter.setBrush(QColor(color_hex))
    bar_w = 6
    for x in (10, 21, 32):
        painter.drawRoundedRect(QRectF(x, 10, bar_w, 28), 3, 3)

    painter.end()
    return QIcon(pixmap)


def launch_app_command(app_dict: dict | str) -> bool:
    """Launches an application using its desktop_name, command, or executable."""
    import subprocess, shutil, logging
    if isinstance(app_dict, str):
        desktop_name = app_dict if app_dict.endswith(".desktop") else app_dict + ".desktop"
        executable = app_dict[:-8] if app_dict.endswith(".desktop") else app_dict
    elif isinstance(app_dict, dict):
        desktop_name = app_dict.get("desktop_name")
        executable = app_dict.get("executable") or app_dict.get("id")
    else:
        return False
    
    if desktop_name and shutil.which("gtk-launch"):
        try:
            dt_id = desktop_name[:-8] if desktop_name.endswith(".desktop") else desktop_name
            subprocess.Popen(["gtk-launch", dt_id], close_fds=True, start_new_session=True)
            return True
        except Exception as e:
            logging.warning(f"gtk-launch failed for '{desktop_name}': {e}")

    if executable:
        path = shutil.which(executable)
        if path:
            try:
                subprocess.Popen([path], close_fds=True, start_new_session=True)
                return True
            except Exception as e:
                logging.error(f"Failed to launch executable '{path}': {e}")
    return False

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
        tray_apps = [app for app in protected_apps if (app.get("show_in_tray", True) if isinstance(app, dict) else True)][:5]
        from ui.theme import resolve_app_icon, composite_tray_icon
        for app in tray_apps:
            if isinstance(app, dict):
                app_id = app.get("id")
                app_name = app.get("name", app_id)
                desktop_name = app.get("desktop_name")
                icon_name = app.get("icon", "")
            else:
                app_id = app
                app_name = app
                desktop_name = app
                icon_name = ""
            
            is_authed = self.main_app.is_app_authorized(app_id)
            display_text = app_name
            
            # Resolve real icon and composite overlay badge
            base_icon = resolve_app_icon(icon_name)
            composited_icon = composite_tray_icon(base_icon, is_locked=not is_authed)
            
            app_action = QAction(display_text, self.menu)
            app_action.setIcon(composited_icon)
            
            # Action triggers
            if not is_authed:
                def make_trigger(d_name=desktop_name):
                    return lambda: self.main_app.trigger_manual_auth(d_name)
                app_action.triggered.connect(make_trigger())
            else:
                def make_open(target_app=app, a_id=app_id):
                    def _handler():
                        resumed = 0
                        if hasattr(self.main_app, 'session_manager'):
                            resumed = self.main_app.session_manager.resume_suspended_processes(a_id)
                        if resumed == 0:
                            launch_app_command(target_app)
                    return _handler
                app_action.triggered.connect(make_open())
                
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
