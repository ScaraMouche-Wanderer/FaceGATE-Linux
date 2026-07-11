import logging
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PySide6.QtCore import Qt

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

class FaceGateTray(QSystemTrayIcon):
    def __init__(self, main_app, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        
        from ui.theme import ACCENT_PURPLE, TEXT_SECONDARY
        # Pre-render state icons
        self.active_icon = create_circle_icon(ACCENT_PURPLE)
        self.inactive_icon = create_circle_icon(TEXT_SECONDARY)
        
        self.setIcon(self.active_icon)
        self.setToolTip("FaceGate-Linux")
        
        # Setup context menu
        self.menu = QMenu()
        # Connect aboutToShow to dynamically rebuild menu options
        self.menu.aboutToShow.connect(self.rebuild_menu)
        self.setContextMenu(self.menu)
        
        self.rebuild_menu()

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
