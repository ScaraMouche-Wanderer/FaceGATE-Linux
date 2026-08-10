"""
SessionManager controller for FaceGATE-Linux.

Manages application unlock authorization states, session timeouts,
pause/disable durations, and relocking events.
"""

import time
import logging
from PySide6.QtCore import QObject, QTimer, Slot

class SessionManager(QObject):
    def __init__(self, config, protected_apps_provider, tray_provider=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.get_protected_apps = protected_apps_provider
        self.get_tray = tray_provider if callable(tray_provider) else (lambda: None)
        
        self.active = True
        self.disabled_until = None
        self.authorized_apps = {}  # app_id -> bool
        self.auth_timestamps = {}  # app_id -> float

        for app in self.get_protected_apps():
            self.authorized_apps[app["id"]] = False

        self.disabled_timer = QTimer(self)
        self.disabled_timer.setSingleShot(True)
        self.disabled_timer.timeout.connect(self.resume)

    def is_active(self) -> bool:
        return self.active

    def is_app_authorized(self, app_id: str) -> bool:
        canonical_id = self.get_app_id_from_desktop(app_id)
        return self.authorized_apps.get(canonical_id, False)

    def get_app_id_from_desktop(self, identifier: str) -> str:
        if not identifier:
            return identifier
        norm_id = identifier[:-8] if identifier.endswith(".desktop") else identifier
        for app in self.get_protected_apps():
            app_id = app.get("id", "")
            desktop_name = app.get("desktop_name", "")
            norm_app_id = app_id[:-8] if app_id.endswith(".desktop") else app_id
            norm_desktop = desktop_name[:-8] if desktop_name.endswith(".desktop") else desktop_name

            if identifier in (app_id, desktop_name) or norm_id in (norm_app_id, norm_desktop):
                return app_id
        return identifier

    def get_app_name(self, identifier: str) -> str:
        for app in self.get_protected_apps():
            if app.get("id") == identifier or app.get("desktop_name") == identifier:
                return app.get("name", identifier)
        return identifier

    def authorize_app(self, app_identifier: str):
        app_id = self.get_app_id_from_desktop(app_identifier)
        protected_ids = {app.get("id") for app in self.get_protected_apps() if app.get("id")}
        if app_id not in protected_ids:
            logging.warning(f"Attempted to authorize non-protected application or pseudo-app '{app_identifier}' (ID: '{app_id}'). Skipping session caching.")
            return

        was_authorized = self.authorized_apps.get(app_id, False)
        self.authorized_apps[app_id] = True
        self.auth_timestamps[app_id] = time.time()
        logging.info(f"State updated: Application '{app_id}' is UNLOCKED.")

        tray = self.get_tray()
        if not was_authorized and self.config.get("behavior.notify_on_auth", True) and tray:
            from PySide6.QtWidgets import QSystemTrayIcon
            app_name = self.get_app_name(app_id)
            tray.showMessage(
                "Application Unlocked",
                f"Access to '{app_name}' has been authorized.",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )

    def relock_app(self, app_id: str, monitor=None):
        canonical_id = self.get_app_id_from_desktop(app_id)
        was_authorized = self.authorized_apps.get(canonical_id, False)
        self.authorized_apps[canonical_id] = False
        self.auth_timestamps.pop(canonical_id, None)
        logging.info(f"State updated: Application '{canonical_id}' is LOCKED.")
        
        if monitor:
            monitor.clear_seen_pids()

        tray = self.get_tray()
        if was_authorized and self.config.get("behavior.notify_on_auth", True) and tray:
            from PySide6.QtWidgets import QSystemTrayIcon
            app_name = self.get_app_name(app_id)
            tray.showMessage(
                "Application Locked",
                f"Access to '{app_name}' has been re-locked.",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )

    @Slot()
    def relock_all(self, monitor=None):
        for app in self.get_protected_apps():
            self.relock_app(app["id"], monitor=monitor)

    @Slot()
    def resume(self, monitor=None):
        self.disabled_timer.stop()
        self.disabled_until = None
        self.active = True

        from locking.launcher_sub import apply_substitution
        try:
            apply_substitution(self.get_protected_apps())
            logging.info("Re-applied launcher substitutions on resume.")
        except Exception as e:
            logging.error(f"Error re-applying launcher substitutions on resume: {e}")

        if monitor:
            monitor.clear_seen_pids()
            if not monitor.isRunning():
                monitor.start()

        tray = self.get_tray()
        if tray:
            tray.update_tray_state()
        logging.info("FaceGate monitor is now ACTIVE.")

    def disable_for(self, minutes: int, verify_admin_cb, monitor=None):
        if verify_admin_cb and not verify_admin_cb("Disable FaceGate"):
            logging.warning("Disable FaceGate: Verification failed.")
            return False

        self.disabled_until = time.time() + (minutes * 60)
        self.active = False
        self.disabled_timer.start(minutes * 60 * 1000)

        from locking.launcher_manager import get_launcher_manager
        try:
            get_launcher_manager().restore_all_launchers()
            logging.info("Restored all launchers before stopping monitor on disable.")
        except Exception as e:
            logging.error(f"Error restoring launchers on disable: {e}")

        if monitor:
            monitor.stop()

        self.authorized_apps.clear()
        self.auth_timestamps.clear()
        if monitor:
            monitor.clear_seen_pids()

        tray = self.get_tray()
        if tray:
            tray.update_tray_state()
        logging.info(f"FaceGate monitor PAUSED for {minutes} minutes.")
        return True

    def get_remaining_disabled_seconds(self) -> float:
        if self.disabled_until:
            return max(0.0, self.disabled_until - time.time())
        return 0.0
