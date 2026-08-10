"""
LifecycleController for FaceGATE-Linux.

Handles D-Bus systemd power state signals (PrepareForSleep) and
desktop screensaver lock events (ActiveChanged) to re-lock sessions.
"""

import logging
from PySide6.QtCore import QObject, Slot, QTimer

class LifecycleController(QObject):
    def __init__(self, config, session_manager_provider, protected_apps_provider, parent=None):
        super().__init__(parent)
        self.config = config
        self.get_session_manager = session_manager_provider if callable(session_manager_provider) else (lambda: session_manager_provider)
        self.get_protected_apps = protected_apps_provider

        # Setup periodic recheck of desktop launcher shadowing
        recheck_interval = int(self.config.get("behavior.launcher_recheck_interval_minutes", 10))
        if recheck_interval > 0:
            self.recheck_timer = QTimer(self)
            self.recheck_timer.timeout.connect(self.recheck_launcher_shadowing)
            self.recheck_timer.start(recheck_interval * 60 * 1000)

        # Connect D-Bus sleep & lock monitors
        from PySide6.QtDBus import QDBusConnection
        
        system_bus = QDBusConnection.systemBus()
        if system_bus.isConnected():
            system_bus.connect(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager",
                "PrepareForSleep",
                self, "handle_prepare_for_sleep"
            )
            logging.info("Connected to systemd PrepareForSleep D-Bus signal.")
            
        session_bus = QDBusConnection.sessionBus()
        if session_bus.isConnected():
            for service in ["org.gnome.ScreenSaver", "org.freedesktop.ScreenSaver", "org.xfce.ScreenSaver"]:
                path = "/org/gnome/ScreenSaver" if "gnome" in service else ("/org/xfce/ScreenSaver" if "xfce" in service else "/ScreenSaver")
                session_bus.connect(
                    service,
                    path,
                    service,
                    "ActiveChanged",
                    self, "handle_screensaver_active_changed"
                )
            logging.info("Connected to ScreenSaver ActiveChanged D-Bus signals.")

    @Slot(bool)
    def handle_prepare_for_sleep(self, starting_sleep: bool):
        if starting_sleep and self.config.get("behavior.lock_on_sleep_or_lock", True):
            logging.info("System preparing for sleep/suspend. Relocking all applications to prevent trespassing.")
            sm = self.get_session_manager()
            if sm:
                sm.relock_all()

    @Slot(bool)
    def handle_screensaver_active_changed(self, active: bool):
        if active and self.config.get("behavior.lock_on_sleep_or_lock", True):
            logging.info("Screensaver/Lock screen activated. Relocking all applications to prevent trespassing.")
            sm = self.get_session_manager()
            if sm:
                sm.relock_all()

    def recheck_launcher_shadowing(self):
        from locking.launcher_sub import check_and_fix_substitutions
        check_and_fix_substitutions(self.get_protected_apps())
        logging.info("Launcher shadowing rechecked and fixed if needed.")
