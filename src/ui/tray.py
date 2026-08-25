from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QPen, QPolygonF
from PySide6.QtCore import Qt, QPointF, QRectF, QSize


def draw_face_emblem(painter: QPainter, s: float, cx: float, cy: float, col: str = "#ffffff", scale: float = 1.0):
    """
    Renders the signature FaceGate biometric face scan emblem:
    4 corner brackets, two eyes, and a biometric mouth curve.
    Scales smoothly and remains ultra-sharp at any resolution.
    """
    emblem_pen = QPen(QColor(col))
    emblem_pen.setWidthF(max(1.0, s * 0.065 * scale))
    emblem_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    emblem_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(emblem_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    
    # 4 Corner brackets
    c_len = s * 0.11 * scale
    x_span = s * 0.26 * scale
    y_span = s * 0.26 * scale
    x1, x2 = cx - x_span, cx + x_span
    y1, y2 = cy - y_span, cy + y_span
    
    # Top-left
    painter.drawLine(QPointF(x1, y1 + c_len), QPointF(x1, y1))
    painter.drawLine(QPointF(x1, y1), QPointF(x1 + c_len, y1))
    # Top-right
    painter.drawLine(QPointF(x2 - c_len, y1), QPointF(x2, y1))
    painter.drawLine(QPointF(x2, y1), QPointF(x2, y1 + c_len))
    # Bottom-left
    painter.drawLine(QPointF(x1, y2 - c_len), QPointF(x1, y2))
    painter.drawLine(QPointF(x1, y2), QPointF(x1 + c_len, y2))
    # Bottom-right
    painter.drawLine(QPointF(x2 - c_len, y2), QPointF(x2, y2))
    painter.drawLine(QPointF(x2, y2), QPointF(x2, y2 - c_len))
    
    # Two eyes (Dots)
    painter.setBrush(QColor(col))
    painter.setPen(Qt.PenStyle.NoPen)
    eye_r = max(0.8, s * 0.05 * scale)
    eye_y = cy - s * 0.06 * scale
    painter.drawEllipse(QPointF(cx - s * 0.13 * scale, eye_y), eye_r, eye_r)
    painter.drawEllipse(QPointF(cx + s * 0.13 * scale, eye_y), eye_r, eye_r)
    
    # Smile / Biometric mouth curve
    painter.setPen(emblem_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    from PySide6.QtGui import QPainterPath
    mouth_path = QPainterPath()
    mouth_path.moveTo(cx - s * 0.11 * scale, cy + s * 0.08 * scale)
    mouth_path.quadTo(cx, cy + s * 0.17 * scale, cx + s * 0.11 * scale, cy + s * 0.08 * scale)
    painter.drawPath(mouth_path)


def create_circle_icon(color_hex: str) -> QIcon:
    """
    Renders a custom circle status icon dynamically at multiple resolutions
    (16, 22, 24, 32, 48, 64, 128) with the recognizable FaceGate biometric face scan emblem.
    """
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        s = float(size)
        cx, cy = s / 2.0, s / 2.0
        border_w = max(1.0, s * 0.05)
        pen = QPen(QColor("#ffffff"))
        pen.setWidthF(border_w)
        painter.setPen(pen)
        painter.setBrush(QColor(color_hex))
        
        margin = border_w / 2.0 + 0.4
        painter.drawEllipse(QRectF(margin, margin, s - 2 * margin, s - 2 * margin))
        draw_face_emblem(painter, s, cx, cy, col="#ffffff", scale=1.0)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def create_square_icon(color_hex: str) -> QIcon:
    """
    Renders a rounded-square status icon at multiple resolutions, featuring
    the distinct FaceGate biometric face scan emblem.
    """
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = float(size)
        cx, cy = s / 2.0, s / 2.0
        border_w = max(1.0, s * 0.05)
        pen = QPen(QColor("#ffffff"))
        pen.setWidthF(border_w)
        painter.setPen(pen)
        painter.setBrush(QColor(color_hex))

        margin = border_w / 2.0 + 0.4
        radius = s * 0.22
        painter.drawRoundedRect(QRectF(margin, margin, s - 2 * margin, s - 2 * margin), radius, radius)
        draw_face_emblem(painter, s, cx, cy, col="#ffffff", scale=1.0)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def create_shield_icon(color_hex: str) -> QIcon:
    """
    Renders a prominent shield glyph at multiple resolutions, embedded with
    the FaceGate biometric protection face emblem.
    """
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = float(size)
        cx, cy = s / 2.0, s * 0.46
        border_w = max(1.0, s * 0.05)
        pen = QPen(QColor("#ffffff"))
        pen.setWidthF(border_w)
        painter.setPen(pen)
        painter.setBrush(QColor(color_hex))

        top = border_w / 2.0 + 0.5
        height = s - border_w - 1.0
        half_w = (s - border_w - 1.0) / 2.0

        poly = QPolygonF([
            QPointF(s / 2.0, top),
            QPointF(s / 2.0 + half_w, top + half_w * 0.45),
            QPointF(s / 2.0 + half_w, top + height * 0.58),
            QPointF(s / 2.0, top + height),
            QPointF(s / 2.0 - half_w, top + height * 0.58),
            QPointF(s / 2.0 - half_w, top + half_w * 0.45),
        ])
        painter.drawPolygon(poly)
        draw_face_emblem(painter, s, cx, cy, col="#ffffff", scale=0.82)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def create_lock_icon(color_hex: str) -> QIcon:
    """
    Renders a bold padlock glyph at multiple resolutions, featuring
    the FaceGate biometric scan emblem inside the lock body.
    """
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = float(size)
        cx = s / 2.0
        border_w = max(1.0, s * 0.05)
        
        # Shackle
        shackle_w = s * 0.46
        shackle_left = cx - shackle_w / 2.0
        shackle_top = border_w + 0.5
        shackle_h = s * 0.44
        shackle_stroke = max(2.2, s * 0.12)
        
        shackle_pen = QPen(QColor("#ffffff"))
        shackle_pen.setWidthF(shackle_stroke + border_w * 1.5)
        shackle_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(shackle_pen)
        painter.drawArc(QRectF(shackle_left, shackle_top, shackle_w, shackle_h), 0, 180 * 16)
        
        shackle_inner_pen = QPen(QColor(color_hex))
        shackle_inner_pen.setWidthF(shackle_stroke)
        shackle_inner_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(shackle_inner_pen)
        painter.drawArc(QRectF(shackle_left, shackle_top, shackle_w, shackle_h), 0, 180 * 16)

        # Lock Body
        body_x = s * 0.08
        body_y = s * 0.38
        body_w = s * 0.84
        body_h = s * 0.56
        body_radius = s * 0.14
        
        body_pen = QPen(QColor("#ffffff"))
        body_pen.setWidthF(border_w)
        painter.setPen(body_pen)
        painter.setBrush(QColor(color_hex))
        painter.drawRoundedRect(QRectF(body_x, body_y, body_w, body_h), body_radius, body_radius)

        # Face emblem inside lock body
        draw_face_emblem(painter, s, cx, body_y + body_h / 2.0, col="#ffffff", scale=0.75)

        painter.end()
        icon.addPixmap(pixmap)
    return icon


def create_gate_icon(color_hex: str) -> QIcon:
    """
    Renders modern FaceGATE vertical security pillars at multiple resolutions,
    with an active biometric laser scan beam across the portal.
    """
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = float(size)
        border_w = max(1.0, s * 0.05)
        bar_w = s * 0.24
        bar_h = s * 0.88
        bar_y = (s - bar_h) / 2.0
        radius = bar_w / 2.0

        bar_x_positions = [s * 0.06, s * 0.38, s * 0.70]

        pen = QPen(QColor("#ffffff"))
        pen.setWidthF(border_w)
        painter.setPen(pen)
        painter.setBrush(QColor(color_hex))

        for x in bar_x_positions:
            painter.drawRoundedRect(QRectF(x, bar_y, bar_w, bar_h), radius, radius)

        # Glowing horizontal scan beam across the gate
        beam_pen = QPen(QColor("#ffffff"))
        beam_pen.setWidthF(max(1.2, s * 0.08))
        beam_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(beam_pen)
        painter.drawLine(QPointF(s * 0.08, s * 0.50), QPointF(s * 0.92, s * 0.50))
        
        # Center scan diamond / node
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(Qt.PenStyle.NoPen)
        node_r = max(1.0, s * 0.08)
        painter.drawEllipse(QPointF(s * 0.50, s * 0.50), node_r, node_r)

        painter.end()
        icon.addPixmap(pixmap)
    return icon


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
        
        # Setup modern quick settings popup control center
        from ui.tray_popup import FaceGateTrayPopup
        self.popup = FaceGateTrayPopup(self.main_app)
        
        # Connect activation signals
        self.activated.connect(self._handle_activated)
        
        # Setup context menu (robust fallback)
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
        if hasattr(self, 'popup') and self.popup and self.popup.isVisible():
            self.popup.refresh_state()

    def toggle_popup(self):
        """Toggles visibility of the modern quick settings popup."""
        if hasattr(self, 'popup') and self.popup:
            if self.popup.isVisible():
                self.popup.hide()
            else:
                self.show_popup()

    def show_popup(self):
        """Opens and anchors the modern quick settings popup."""
        if hasattr(self, 'popup') and self.popup:
            self.popup.show_at_tray(self.geometry(), QCursor.pos())

    def hide_popup(self):
        """Hides the quick settings popup."""
        if hasattr(self, 'popup') and self.popup:
            self.popup.hide()

    def _handle_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handles left click, double click, or middle click on tray icon."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_popup()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.main_app.relock_all()

    def rebuild_menu(self):
        """Dynamically rebuilds the menu items to reflect live state."""
        self.menu.clear()
        
        from ui.theme import create_monochrome_icon, get_colors
        c = get_colors()
        text_primary = c.get("TEXT_PRIMARY", "#f3f4f6")
        text_secondary = c.get("TEXT_SECONDARY", "#9ca3af")
        danger_col = c.get("DANGER_RED", "#ef4444")
        success_col = c.get("SUCCESS_GREEN", "#10b981")
        
        # 1. Status header
        is_active = self.main_app.is_active()
        if is_active:
            status_text = "FaceGate: Active & Guarding"
            status_icon = create_monochrome_icon("shield", text_primary, 24)
        elif self.main_app.disabled_until:
            remaining = int(self.main_app.get_remaining_disabled_seconds())
            mins, secs = divmod(max(0, remaining), 60)
            status_text = f"FaceGate: Paused ({mins:02d}:{secs:02d} left)"
            status_icon = create_monochrome_icon("pause", text_secondary, 24)
        else:
            status_text = "FaceGate: Inactive (Disabled)"
            status_icon = create_monochrome_icon("shield", text_secondary, 24)
                
        status_action = QAction(status_text, self.menu)
        status_action.setEnabled(False)
        status_action.setIcon(status_icon)
        self.menu.addAction(status_action)
        
        # 2. Open Quick Control Center popup action
        control_action = QAction("Open Quick Control Center...", self.menu)
        control_action.setIcon(create_monochrome_icon("grid", text_primary, 24))
        control_action.triggered.connect(self.show_popup)
        self.menu.addAction(control_action)
        
        self.menu.addSeparator()
        
        # 3. Quick Actions: Quick Scan & Relock All
        quick_scan_action = QAction("Quick Scan (Authenticate Now)", self.menu)
        quick_scan_action.setIcon(create_monochrome_icon("scan", text_primary, 24))
        quick_scan_action.triggered.connect(lambda: self.main_app.trigger_manual_auth("quick_scan"))
        self.menu.addAction(quick_scan_action)
        
        protected_apps = self.main_app.get_protected_apps()
        has_unlocked = any(self.main_app.is_app_authorized(app["id"]) for app in protected_apps if isinstance(app, dict))
        
        relock_all_action = QAction("Re-lock All Apps", self.menu)
        relock_all_action.setIcon(create_monochrome_icon("lock", text_primary, 24))
        relock_all_action.triggered.connect(self.main_app.relock_all)
        relock_all_action.setEnabled(is_active and has_unlocked)
        self.menu.addAction(relock_all_action)
        
        # 4. Pause / Resume Protection (Direct top-level action with HD clock icon on the left)
        if is_active:
            pause_action = QAction("Pause Protection (15 min)", self.menu)
            pause_action.setIcon(create_monochrome_icon("clock", text_primary, 24))
            pause_action.triggered.connect(lambda: self.main_app.disable_for(15))
            self.menu.addAction(pause_action)
        else:
            resume_action = QAction("Resume FaceGate Protection", self.menu)
            resume_action.setIcon(create_monochrome_icon("play", success_col, 24))
            resume_action.triggered.connect(self.main_app.resume)
            self.menu.addAction(resume_action)
            
        self.menu.addSeparator()
        
        # 5. Protected apps rows
        tray_apps = [app for app in protected_apps if (app.get("show_in_tray", True) if isinstance(app, dict) else True)][:5]
        from ui.theme import resolve_app_icon, composite_tray_icon
        
        if tray_apps:
            apps_header = QAction("Protected Apps", self.menu)
            apps_header.setIcon(create_monochrome_icon("apps", text_secondary, 22))
            apps_header.setEnabled(False)
            self.menu.addAction(apps_header)
            
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
                state_tag = "(Unlocked)" if is_authed else "(Locked)"
                display_text = f"{app_name}  {state_tag}"
                
                base_icon = resolve_app_icon(icon_name)
                composited_icon = composite_tray_icon(base_icon, is_locked=not is_authed)
                
                app_action = QAction(display_text, self.menu)
                app_action.setIcon(composited_icon)
                
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
        
        # 6. Settings & Enrollment
        settings_action = QAction("Settings...", self.menu)
        settings_action.setIcon(create_monochrome_icon("gear", text_primary, 24))
        settings_action.triggered.connect(self.main_app.open_settings)
        self.menu.addAction(settings_action)

        enroll_action = QAction("Enroll Face...", self.menu)
        enroll_action.setIcon(create_monochrome_icon("user", text_primary, 24))
        enroll_action.triggered.connect(self.main_app.open_enrollment)
        self.menu.addAction(enroll_action)
        
        self.menu.addSeparator()
        
        # 7. Quit
        quit_action = QAction("Quit FaceGate", self.menu)
        quit_action.setIcon(create_monochrome_icon("power", danger_col, 24))
        quit_action.triggered.connect(self.main_app.quit_app)
        self.menu.addAction(quit_action)

