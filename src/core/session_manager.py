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
            app_id = app["id"] if isinstance(app, dict) else app
            self.authorized_apps[app_id] = False

        self.disabled_timer = QTimer(self)
        self.disabled_timer.setSingleShot(True)
        self.disabled_timer.timeout.connect(self.resume)

    def is_active(self) -> bool:
        return self.active

    def is_app_authorized(self, app_id: str) -> bool:
        if not app_id:
            return False
        canonical_id = self.get_app_id_from_desktop(app_id)
        if self.authorized_apps.get(canonical_id, False):
            return True
        if self.authorized_apps.get(app_id, False):
            return True
        norm_id = app_id[:-8] if app_id.endswith(".desktop") else app_id
        return any(self.authorized_apps.get(k, False) for k in (norm_id, norm_id + ".desktop"))

    def get_app_id_from_desktop(self, identifier: str) -> str:
        if not identifier:
            return identifier
        norm_id = identifier[:-8] if identifier.endswith(".desktop") else identifier
        for app in self.get_protected_apps():
            if isinstance(app, dict):
                app_id = app.get("id", "")
                desktop_name = app.get("desktop_name", "")
                norm_app_id = app_id[:-8] if app_id.endswith(".desktop") else app_id
                norm_desktop = desktop_name[:-8] if desktop_name.endswith(".desktop") else desktop_name

                if identifier in (app_id, desktop_name) or norm_id in (norm_app_id, norm_desktop):
                    return app_id or desktop_name or identifier
            elif isinstance(app, str):
                norm_app = app[:-8] if app.endswith(".desktop") else app
                if identifier == app or norm_id == norm_app:
                    return app
        return identifier

    def get_app_name(self, identifier: str) -> str:
        for app in self.get_protected_apps():
            if isinstance(app, dict):
                if app.get("id") == identifier or app.get("desktop_name") == identifier:
                    return app.get("name", identifier)
            elif isinstance(app, str):
                if app == identifier:
                    return identifier
        return identifier

    def authorize_app(self, app_identifier: str):
        app_id = self.get_app_id_from_desktop(app_identifier)
        protected_ids = set()
        for app in self.get_protected_apps():
            if isinstance(app, dict):
                if app.get("id"):
                    protected_ids.add(app["id"])
                if app.get("desktop_name"):
                    protected_ids.add(app["desktop_name"])
            elif isinstance(app, str):
                protected_ids.add(app)

        if app_id not in protected_ids and app_identifier not in protected_ids:
            logging.warning(f"Attempted to authorize non-protected application or pseudo-app '{app_identifier}' (ID: '{app_id}'). Skipping session caching.")
            return

        was_authorized = self.authorized_apps.get(app_id, False)
        self.authorized_apps[app_id] = True
        self.authorized_apps[app_identifier] = True
        self.auth_timestamps[app_id] = time.time()
        self.auth_timestamps[app_identifier] = time.time()
        logging.info(f"State updated: Application '{app_id}' ('{app_identifier}') is UNLOCKED.")

        # Resume any process that was suspended prior to authorization
        self.resume_suspended_processes(app_id)

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

    def resume_suspended_processes(self, app_identifier: str) -> int:
        """Sends SIGCONT to any running processes for app_identifier that are in SIGSTOP state."""
        import psutil, os, signal
        canonical_id = self.get_app_id_from_desktop(app_identifier)
        resumed = 0
        
        target_app = None
        for app in self.get_protected_apps():
            if isinstance(app, dict):
                p_id = app.get("id", "")
                p_desk = app.get("desktop_name", "")
                if canonical_id in (p_id, p_desk) or app_identifier in (p_id, p_desk):
                    target_app = app
                    break
        if not target_app:
            return 0

        exec_name = target_app.get("executable") or target_app.get("id") or ""
        if not exec_name:
            return 0

        exec_base = os.path.basename(exec_name).lower()

        for proc in psutil.process_iter(['pid', 'name', 'exe', 'status']):
            try:
                name = (proc.info['name'] or "").lower()
                exe = (proc.info['exe'] or "").lower()
                status = proc.info['status']

                if exec_base in name or exec_base in os.path.basename(exe):
                    if status == psutil.STATUS_STOPPED:
                        logging.info(f"Resuming suspended process '{proc.info['name']}' (PID: {proc.info['pid']}) via SIGCONT.")
                        os.kill(proc.info['pid'], signal.SIGCONT)
                        resumed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return resumed

    def relock_app(self, app_id: str, monitor=None):
        canonical_id = self.get_app_id_from_desktop(app_id)
        norm_id = canonical_id[:-8] if canonical_id.endswith(".desktop") else canonical_id
        keys_to_clear = {canonical_id, app_id, norm_id, norm_id + ".desktop"}
        
        was_authorized = any(self.authorized_apps.get(k, False) for k in keys_to_clear)
        for k in keys_to_clear:
            self.authorized_apps[k] = False
            self.auth_timestamps.pop(k, None)

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
