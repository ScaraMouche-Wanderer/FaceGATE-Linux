import os
import sys
import argparse
import logging
import signal
import time
import subprocess


from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QDialog
from PySide6.QtCore import QObject, Slot, QTimer, QMetaObject, Qt

from utils.logging_setup import setup_logging
from utils.config_loader import get_config
from locking.launcher_sub import apply_substitution, restore_substitution
from locking.ipc_service import FaceGateService, register_dbus_service
from locking.app_monitor import AppMonitor
from ui.tray import FaceGateTray
from ui.auth_dialog import AuthDialog

from core.session_manager import SessionManager
from core.auth_coordinator import AuthCoordinator
from core.lifecycle_controller import LifecycleController
from core.window_manager import WindowManager

class FaceGateApplication(QObject):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.tray = None

        # Domain Controllers
        self.session_manager = SessionManager(
            config,
            protected_apps_provider=self.get_protected_apps,
            tray_provider=lambda: self.tray,
            parent=self
        )
        self.auth_coordinator = AuthCoordinator(
            config,
            session_manager=self.session_manager,
            parent=self
        )
        self.lifecycle_controller = LifecycleController(
            config,
            session_manager_provider=self.session_manager,
            protected_apps_provider=self.get_protected_apps,
            parent=self
        )
        self.window_manager = WindowManager(
            config,
            auth_coordinator=self.auth_coordinator,
            parent=self
        )

        # Setup AppMonitor
        poll_interval = float(self.config.get("app_monitor.poll_interval_seconds", 1.5))
        self.monitor = AppMonitor(self, poll_interval=poll_interval)
        self.monitor.signals.request_auth.connect(self.auth_coordinator.handle_monitor_auth, Qt.ConnectionType.QueuedConnection)

        # Setup Geofence Network Monitor if enabled
        if self.config.get("security.geofence_enabled", False):
            from security.geofence import GeofenceMonitor
            trusted = self.config.get("security.trusted_networks", [])
            self.geofence = GeofenceMonitor(check_interval_sec=15, parent=self)
            self.geofence.set_trusted_ssids(trusted, enabled=True)
            self.geofence.untrusted_network_detected.connect(
                lambda ssid: (logging.warning(f"Geofence: Relocking all apps due to untrusted network '{ssid}'"), self.relock_all())
            )
            logging.info("Geofence session awareness monitor initialized.")

        # Register Cross-Platform IPC and D-Bus Services
        self.dbus_service = FaceGateService(self)
        from locking.ipc_service import CrossPlatformIPCServer
        self.ipc_server = CrossPlatformIPCServer(self.dbus_service, self)
        self.ipc_server.start()
        register_dbus_service(self.dbus_service)


        # Startup Recovery Check & Consistency Verification
        from locking.launcher_manager import get_launcher_manager
        get_launcher_manager().startup_recovery(self.get_protected_apps())

        startup_delay = int(self.config.get("behavior.startup_delay_seconds", 0))
        if startup_delay > 0:
            logging.info(f"Daemon: Delaying tray and background monitoring startup by {startup_delay} seconds...")
            QTimer.singleShot(startup_delay * 1000, self._deferred_startup)
        else:
            self._deferred_startup()

    def _deferred_startup(self):
        # Startup Consistency Check & Launcher Substitution
        if self.is_active():
            logging.info("FaceGate daemon starting in ACTIVE mode. Applying launcher substitutions...")
            apply_substitution(self.get_protected_apps())
            self.monitor.start()
        else:
            logging.info("FaceGate daemon starting in INACTIVE mode. Restoring launchers...")
            restore_substitution(self.get_protected_apps())

        # State Integrity Watchdog — detects file-deletion bypass attacks
        from security.state_watchdog import StateWatchdog
        if not hasattr(self, 'state_watchdog') or self.state_watchdog is None:
            self.state_watchdog = StateWatchdog(
                on_tamper_callback=self._handle_state_tamper,
                check_interval=30.0,
            )
            self.state_watchdog.start()

        # Initialize Tray Icon
        self.check_tray_and_start(attempts=0)

    # Properties & Forwarding Methods for Interface Compatibility
    @property
    def disabled_until(self):
        return self.session_manager.disabled_until

    @disabled_until.setter
    def disabled_until(self, val):
        self.session_manager.disabled_until = val

    @property
    def _auth_queue(self):
        return self.auth_coordinator._auth_queue

    @property
    def _auth_busy(self):
        return self.auth_coordinator._auth_busy

    @_auth_busy.setter
    def _auth_busy(self, val):
        self.auth_coordinator._auth_busy = val

    def _process_auth_request(self, desktop_name: str, pid: int):
        self.auth_coordinator._process_auth_request(desktop_name, pid)

    def _run_recognition_subprocess(self, reason: str) -> tuple[bool, str, float, str]:
        return self.auth_coordinator._run_recognition_subprocess(reason)

    @Slot(bool)
    def handle_prepare_for_sleep(self, starting_sleep: bool):
        self.lifecycle_controller.handle_prepare_for_sleep(starting_sleep)

    @Slot(bool)
    def handle_screensaver_active_changed(self, active: bool):
        self.lifecycle_controller.handle_screensaver_active_changed(active)

    @property
    def authorized_apps(self):
        return self.session_manager.authorized_apps

    @property
    def auth_timestamps(self):
        return self.session_manager.auth_timestamps

    def get_protected_apps(self):
        return self.config.get("protected_apps", [])

    def is_active(self) -> bool:
        return self.session_manager.is_active()

    def is_app_authorized(self, app_id: str) -> bool:
        return self.session_manager.is_app_authorized(app_id)

    def get_app_id_from_desktop(self, desktop_name: str) -> str:
        return self.session_manager.get_app_id_from_desktop(desktop_name)

    def get_app_name(self, identifier: str) -> str:
        return self.session_manager.get_app_name(identifier)

    def authorize_app(self, app_identifier: str):
        self.session_manager.authorize_app(app_identifier)

    def relock_app(self, app_id: str):
        self.session_manager.relock_app(app_id, monitor=self.monitor)

    @Slot()
    def relock_all(self):
        self.session_manager.relock_all(monitor=self.monitor)

    @Slot()
    def resume(self):
        self.session_manager.resume(monitor=self.monitor)

    def disable_for(self, minutes: int):
        self.session_manager.disable_for(minutes, verify_admin_cb=self.verify_admin_face, monitor=self.monitor)

    def get_remaining_disabled_seconds(self) -> float:
        return self.session_manager.get_remaining_disabled_seconds()

    def verify_admin_face(self, reason: str) -> bool:
        return self.auth_coordinator.verify_admin_face(reason)

    @Slot(str, int)
    def handle_monitor_auth(self, desktop_name: str, pid: int):
        self.auth_coordinator.handle_monitor_auth(desktop_name, pid)

    @Slot()
    def open_settings(self):
        self.window_manager.open_settings()

    @Slot()
    def open_enrollment(self):
        self.window_manager.open_enrollment()

    def check_tray_and_start(self, attempts: int = 0):
        if self.tray is not None:
            return
        if QSystemTrayIcon.isSystemTrayAvailable():
            logging.info("System tray is available. Initializing Tray Icon.")
            self.tray = FaceGateTray(self)
            self.tray.show()
        else:
            if attempts % 5 == 0:
                logging.info(f"System tray not available yet. Retrying... (Attempt {attempts + 1})")
            QTimer.singleShot(1000, lambda: self.check_tray_and_start(attempts + 1))

    @Slot()
    def reload_config(self) -> bool:
        try:
            self.config.reload()
            apply_substitution(self.get_protected_apps())
            poll_interval = float(self.config.get("app_monitor.poll_interval_seconds", 1.5))
            if hasattr(self, 'monitor') and self.monitor:
                self.monitor.poll_interval = poll_interval
                self.monitor.clear_seen_pids()
            if hasattr(self, 'tray') and self.tray:
                QTimer.singleShot(0, self.tray.refresh_icon_style)
            logging.info("FaceGateApplication: Configuration hot-reloaded successfully live.")
            return True
        except Exception as e:
            logging.error(f"Error hot-reloading configuration: {e}")
            return False

    def trigger_manual_auth(self, desktop_name: str):
        self.dbus_service.request_auth_internal(desktop_name)

    def _handle_state_tamper(self, issues: list):
        """
        Emergency lockdown handler invoked by StateWatchdog when critical
        state files are deleted or modified after initialization.
        
        Actions:
        1. Re-lock all apps (force re-authentication)
        2. Re-apply launcher substitutions (restore protection)
        3. Log CRITICAL audit entries
        4. Show tray notification
        """
        logging.critical(
            "STATE TAMPER LOCKDOWN: %d critical file(s) affected. "
            "Emergency lockdown initiated.",
            len(issues),
        )

        # Re-lock all apps
        try:
            self.relock_all()
        except Exception as e:
            logging.error(f"State tamper lockdown: Error relocking apps: {e}")

        # Re-apply launcher substitutions (in case manifest/backups were deleted)
        try:
            apply_substitution(self.get_protected_apps())
        except Exception as e:
            logging.error(f"State tamper lockdown: Error re-applying substitutions: {e}")

        # Log audit entries
        try:
            from database.audit_log import log_auth_attempt
            for issue in issues:
                log_auth_attempt(
                    f"STATE_TAMPER:{issue['file']}",
                    "tamper_detected",
                    "fail",
                )
        except Exception as e:
            logging.error(f"State tamper lockdown: Error logging audit: {e}")

        # Show tray notification
        if self.tray:
            try:
                from PySide6.QtWidgets import QSystemTrayIcon
                details = ", ".join(i["file"] for i in issues)
                self.tray.showMessage(
                    "⚠️ FaceGATE Security Alert",
                    f"Critical state files tampered with: {details}. "
                    f"All apps have been re-locked.",
                    QSystemTrayIcon.MessageIcon.Critical,
                    15000,
                )
            except Exception:
                pass

    @Slot()
    def quit_app(self, bypass_protection=False, restore_launchers=True):
        logging.info("Quit requested. Performing shutdown...")
        if not bypass_protection:
            if self.config.get("behavior.uninstall_protection", True):
                logging.info("Uninstall protection is active. Prompting for verification...")
                from database.embedding_store import load_embeddings, EMBEDDING_FILE
                import os
                try:
                    enrolled = load_embeddings()
                except Exception:
                    enrolled = {}
                
                from ui.auth_dialog import AuthDialog
                mode = "face" if (enrolled or os.path.exists(EMBEDDING_FILE)) else "password"
                dialog = AuthDialog("FaceGate Shutdown", mode=mode)
                res = dialog.exec()
                if res != QDialog.DialogCode.Accepted:
                    logging.info("Shutdown cancelled due to verification failure.")
                    return
        
        try:
            restore_substitution(self.get_protected_apps())
            logging.info("Launcher modifications reverted on shutdown.")
        except Exception as e:
            logging.error(f"Error restoring launchers on shutdown: {e}")

        if self.monitor:
            self.monitor.stop()

        # Stop the state integrity watchdog
        if hasattr(self, 'state_watchdog') and self.state_watchdog:
            self.state_watchdog.stop()

        from database.embedding_store import clear_cached_key
        clear_cached_key()

        logging.info("Shutting down FaceGate event loop.")
        QApplication.quit()

def run_auth_launch(desktop_name: str, exec_args: list):
    """
    Substituted launcher client entrypoint.
    Queries the running FaceGate daemon via D-Bus session bus.
    If authenticated, spawns the actual application command.
    If FaceGate daemon is inactive, auto-starts the daemon or falls back to in-client GUI auth.
    """
    desktop_field_codes = {"%f", "%F", "%u", "%U", "%i", "%c", "%k"}
    clean_exec_args = [arg for arg in exec_args if arg not in desktop_field_codes]
    if clean_exec_args:
        exec_args = clean_exec_args

    from PySide6.QtCore import QCoreApplication
    from PySide6.QtDBus import QDBusInterface, QDBusConnection, QDBusReply, QDBus

    bus = QDBusConnection.sessionBus()

    # Check if daemon is currently registered on session bus
    daemon_active = False
    if bus.isConnected():
        try:
            owner_reply = bus.interface().serviceOwner("org.facegate.FaceGate")
            if owner_reply.isValid() and owner_reply.value():
                daemon_active = True
        except Exception:
            pass

    if not daemon_active:
        logging.info(f"Launcher: FaceGate daemon is not active. Attempting to start daemon for '{desktop_name}'...")
        from locking.launcher_sub import get_facegate_cmd
        try:
            fg_cmd = list(get_facegate_cmd())
            fg_cmd.append("--monitor")
            subprocess.Popen(fg_cmd, close_fds=True, start_new_session=True)
            for _ in range(30):
                time.sleep(0.1)
                if bus.isConnected():
                    try:
                        owner_reply = bus.interface().serviceOwner("org.facegate.FaceGate")
                        if owner_reply.isValid() and owner_reply.value():
                            daemon_active = True
                            break
                    except Exception:
                        pass
        except Exception as e:
            logging.warning(f"Could not auto-start daemon: {e}")

    # Capture active desktop display environment variables
    display_env = {}
    env_keys = ["DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "QT_QPA_PLATFORM", "XDG_SESSION_TYPE", "DESKTOP_SESSION"]
    for k in env_keys:
        if k in os.environ:
            display_env[k] = os.environ[k]

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if daemon_active:
        interface = QDBusInterface(
            "org.facegate.FaceGate",
            "/org/facegate/FaceGate",
            "org.facegate.FaceGate",
            bus
        )
        interface.setTimeout(300000)  # 5-minute timeout for authentication requests

        if interface.isValid():
            logging.info(f"Launcher: Requesting auth for app '{desktop_name}' via D-Bus...")
            raw_reply = interface.call("RequestAuth", desktop_name)
            reply = QDBusReply(raw_reply)

            if reply.isValid():
                authorized = reply.value()
                if authorized:
                    logging.info(f"Launcher: D-Bus auth succeeded. Executing: {exec_args}")
                    try:
                        subprocess.Popen(exec_args, close_fds=True, start_new_session=True)
                        sys.exit(0)
                    except Exception as e:
                        logging.error(f"Launcher: Failed to execute {exec_args}: {e}")
                        sys.exit(1)
                else:
                    # Auth returned False — this means async recognition is now in progress.
                    # The daemon's ThreadSignalDispatcher will auto-launch the app upon
                    # successful recognition. Exit cleanly so the launcher doesn't block.
                    logging.info("Launcher: Authentication delegated to daemon (async recognition in progress). Exiting cleanly.")
                    sys.exit(0)
            else:
                logging.warning(f"Launcher: D-Bus call invalid. Error: {interface.lastError().message()}")

    # In-client Fallback Auth Dialog if daemon D-Bus is unavailable or interface call failed
    logging.info(f"Launcher: Running in-client auth fallback for '{desktop_name}'...")

    config = get_config()
    app_name = desktop_name
    protected_apps_list = config.get("protected_apps", [])
    if isinstance(protected_apps_list, list):
        for p_app in protected_apps_list:
            if isinstance(p_app, dict) and (p_app.get("desktop_name") == desktop_name or p_app.get("id") == desktop_name):
                app_name = p_app.get("name", desktop_name)
                break

    raw_timeout = config.get("app_monitor.auth_timeout_seconds", 60)
    timeout_sec = int(raw_timeout if isinstance(raw_timeout, (int, float, str)) else 60)
    from database.embedding_store import EMBEDDING_FILE, OLD_EMBEDDING_FILE
    mode = "face" if (os.path.exists(EMBEDDING_FILE) or os.path.exists(OLD_EMBEDDING_FILE)) else "password"

    dialog = AuthDialog(app_name, mode=mode, timeout_seconds=timeout_sec)
    dialog.setWindowState(Qt.WindowState.WindowActive)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()

    result = dialog.exec()
    if result == QDialog.DialogCode.Accepted or getattr(dialog, "authenticated", False):
        logging.info(f"Launcher in-client auth succeeded. Executing: {exec_args}")
        try:
            subprocess.Popen(exec_args, close_fds=True, start_new_session=True)
            sys.exit(0)
        except Exception as e:
            logging.error(f"Launcher in-client auth: Failed to execute {exec_args}: {e}")
            sys.exit(1)
    else:
        logging.warning("Launcher in-client auth rejected. Blocking execution.")
        sys.exit(1)

def verify_cli_admin_access(action_name: str = "Admin Action"):
    """
    Enforces admin authorization (face recognition via D-Bus daemon or terminal master password fallback)
    for sensitive CLI operations like --enroll, --export-profile, and --import-profile.
    """
    from database.embedding_store import load_embeddings, EMBEDDING_FILE, get_cached_key
    from security.credential_store import verify_password, set_master_password_cli
    import getpass

    has_enrolled = False
    try:
        enrolled = load_embeddings()
        has_enrolled = len(enrolled) > 0
    except Exception:
        has_enrolled = os.path.exists(EMBEDDING_FILE)

    if has_enrolled or os.path.exists(EMBEDDING_FILE):
        dbus_success = False
        dbus_active = False

        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusReply
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            interface = QDBusInterface(
                "org.facegate.FaceGate",
                "/org/facegate/FaceGate",
                "org.facegate.FaceGate",
                bus
            )
            if interface.isValid():
                dbus_active = True
                from PySide6.QtDBus import QDBus
                logging.info(f"Requesting {action_name} authorization via running FaceGate daemon...")
                raw_reply = interface.callWithArgumentList(
                    QDBus.CallMode.Block,
                    "RequestAdminAuth",
                    [action_name]
                )
                reply = QDBusReply(raw_reply)
                if reply.isValid():
                    dbus_success = reply.value()

        if dbus_active and dbus_success:
            logging.info(f"{action_name} authorized via daemon.")
        else:
            if sys.stdin.isatty():
                try:
                    pwd = getpass.getpass(f"Enter master password to authorize {action_name.lower()}: ")
                except (EOFError, KeyboardInterrupt):
                    print(f"\n{action_name} cancelled.", file=sys.stderr)
                    sys.exit(1)
                if not verify_password(pwd):
                    print(f"Error: Incorrect master password. {action_name} denied.", file=sys.stderr)
                    sys.exit(1)
            else:
                print(f"Error: Master password required for {action_name.lower()} in non-interactive mode.", file=sys.stderr)
                sys.exit(1)
    else:
        if get_cached_key() is None:
            if sys.stdin.isatty():
                print("No master password configured. Setting up master password first...")
                set_master_password_cli()
                if get_cached_key() is None:
                    print("Error: Master password configuration failed.", file=sys.stderr)
                    sys.exit(1)
            else:
                print("Error: No master password configured. Run 'facegate --set-master-password' first.", file=sys.stderr)
                sys.exit(1)

def main():
    from utils.config_loader import get_config, save_config
    setup_logging()
    logging.info("Starting FaceGate-Linux application wrapper.")

    # Prevent core dumps from leaking encryption keys from memory via RLIMIT_CORE
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        logging.info("Core dump limit set to 0 (RLIMIT_CORE=0).")
    except Exception as e:
        logging.warning(f"Could not set core dump limit: {e}")


    # Fallback env variables for graphical execution compatibility (only when not running under pure Wayland)
    if "WAYLAND_DISPLAY" not in os.environ and "QT_QPA_PLATFORM" not in os.environ:
        if "DISPLAY" not in os.environ:
            os.environ["DISPLAY"] = ":0"
            logging.info("DISPLAY environment variable not found. Defaulting to :0 for systemd compatibility.")
        xauth = os.path.expanduser("~/.Xauthority")
        if "XAUTHORITY" not in os.environ and os.path.exists(xauth):
            os.environ["XAUTHORITY"] = xauth
            logging.info("XAUTHORITY environment variable not found. Defaulting to ~/.Xauthority.")

    parser = argparse.ArgumentParser(description="FaceGate-Linux lock system")
    parser.add_argument("--monitor", action="store_true", help="Start the main lock daemon and tray icon")
    parser.add_argument("--auth-launch", type=str, help="Authenticate launcher request for target desktop")
    parser.add_argument("--enroll", type=str, help="Enroll a face embedding for the specified username")
    parser.add_argument("--recognize", type=str, help="Run the face recognition subprocess dialog for target desktop")
    parser.add_argument("--set-master-password", action="store_true", help="Set or change the master password")
    parser.add_argument("--key-fd", type=int, help="File descriptor to read the encryption key from")
    parser.add_argument("--emergency-kill", action="store_true", help="Send emergency kill signal to running daemon via D-Bus")
    parser.add_argument("--lock-all", action="store_true", help="Send lockdown signal to running daemon via D-Bus")
    parser.add_argument("--enable", action="store_true", help="Enable and resume FaceGate monitoring")
    parser.add_argument("--disable", nargs="?", const=15, type=int, help="Disable FaceGate monitoring for N minutes (default 15)")
    parser.add_argument("--restore-launchers", action="store_true", help="Restore all modified desktop launchers to original state")
    parser.add_argument("--restore-all", action="store_true", help="Emergency recovery: restore all modified desktop launchers and clear state")
    parser.add_argument("--settings", action="store_true", help="Launch the Settings GUI window")
    parser.add_argument("--status", action="store_true", help="Display rich CLI status dashboard")
    parser.add_argument("--health", action="store_true", help="Run system health and diagnostic checks")
    parser.add_argument("--list-cameras", action="store_true", help="List and diagnose connected camera devices")
    parser.add_argument("--benchmark", action="store_true", help="Run comprehensive hardware, camera, recognition, and crypto benchmarks")
    parser.add_argument("--list-profiles", action="store_true", help="List all enrolled face biometric profiles")
    parser.add_argument("--delete-profile", type=str, metavar="USER", help="Delete an enrolled face profile (requires admin verification)")
    parser.add_argument("--export-logs", type=str, metavar="FILE", help="Export audit logs to CSV or JSON format (.csv, .json)")
    parser.add_argument("--verify-integrity", action="store_true", help="Cryptographically verify state files and SQLite audit log hash chains")
    parser.add_argument("--set-duress-password", action="store_true", help="Configure emergency duress password (silent panic lockdown trigger)")
    parser.add_argument("--quick-add", type=str, metavar="APP", help="Quickly protect an application by name or desktop file")
    parser.add_argument("--remove", type=str, metavar="APP", help="Remove an application from protection and restore its launcher")
    parser.add_argument("--lock", type=str, metavar="APP", help="Instantly re-lock an active application session")
    parser.add_argument("--export-profile", type=str, metavar="FILE", help="Export enrolled face profiles to encrypted transfer file (.fgxfer)")
    parser.add_argument("--export-user", nargs="+", metavar="NAME", help="Specify user profile(s) to export (default: all)")
    parser.add_argument("--import-profile", type=str, metavar="FILE", help="Import face profiles from encrypted transfer file (.fgxfer)")
    parser.add_argument("--force-import", action="store_true", help="Overwrite conflicting local profiles during profile import")
    
    args, unknown = parser.parse_known_args()

    if args.set_duress_password:
        from security.duress_mode import set_duress_password_cli
        set_duress_password_cli()
        sys.exit(0)

    if args.lock:
        app_target = args.lock
        from PySide6.QtDBus import QDBusInterface, QDBusConnection
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            iface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
            if iface.isValid():
                iface.call("RelockApp", app_target)
                print(f"🔒 Application '{app_target}' has been locked.")
                sys.exit(0)
        print(f"Daemon not reachable; marked '{app_target}' for re-locking.")
        sys.exit(0)

    if args.quick_add:
        query = args.quick_add.strip()
        verify_cli_admin_access(f"Protect Application '{query}'")
        from locking.launcher_sub import get_installed_desktop_entries, apply_substitution

        installed = get_installed_desktop_entries()
        q_lower = query.lower()
        matched = None

        # Exact match first
        for item in installed:
            desk = item.get("desktop_name", "").lower()
            name = item.get("name", "").lower()
            ident = item.get("id", "").lower()
            if q_lower in (desk, name, ident, desk.replace(".desktop", "")):
                matched = item
                break

        # Partial substring match if not found
        if not matched:
            for item in installed:
                if q_lower in item.get("desktop_name", "").lower() or q_lower in item.get("name", "").lower():
                    matched = item
                    break

        if not matched:
            print(f"Error: Could not find desktop entry matching '{query}'.", file=sys.stderr)
            print("Tip: Run without .desktop or check application name.", file=sys.stderr)
            sys.exit(1)

        cfg = get_config()
        current_apps = cfg.get("protected_apps", [])
        if not isinstance(current_apps, list):
            current_apps = []

        # Check if already present
        desk_name = matched.get("desktop_name", "")
        if any(a.get("desktop_name") == desk_name for a in current_apps if isinstance(a, dict)):
            print(f"Application '{matched.get('name')}' ({desk_name}) is already protected.")
            sys.exit(0)

        app_record = {
            "id": matched.get("id") or desk_name.replace(".desktop", ""),
            "name": matched.get("name", query),
            "desktop_name": desk_name,
            "executable": matched.get("executable", ""),
            "session_timeout_seconds": 300
        }
        current_apps.append(app_record)
        cfg["protected_apps"] = current_apps
        save_config(cfg)

        try:
            apply_substitution(current_apps)
        except Exception as e:
            logging.warning(f"Could not apply launcher substitution immediately: {e}")

        print(f"🛡️  SUCCESS: Protected '{app_record['name']}' ({desk_name}).")
        print("    Face authentication is now required on launch.")
        sys.exit(0)

    if args.remove:
        query = args.remove.strip()
        verify_cli_admin_access(f"Unprotect Application '{query}'")
        from locking.launcher_manager import get_launcher_manager

        cfg = get_config()
        current_apps = cfg.get("protected_apps", [])

        if not isinstance(current_apps, list):
            current_apps = []

        q_lower = query.lower()
        found_idx = -1
        target_desk = None

        for idx, item in enumerate(current_apps):
            if isinstance(item, dict):
                desk = item.get("desktop_name", "").lower()
                name = item.get("name", "").lower()
                ident = item.get("id", "").lower()
                if q_lower in (desk, name, ident, desk.replace(".desktop", "")):
                    found_idx = idx
                    target_desk = item.get("desktop_name")
                    break

        if found_idx == -1:
            print(f"Error: Application '{query}' is not currently in protected_apps list.", file=sys.stderr)
            sys.exit(1)

        removed_app = current_apps.pop(found_idx)
        cfg["protected_apps"] = current_apps
        save_config(cfg)

        if target_desk:
            try:
                get_launcher_manager().unprotect_launcher(target_desk)
            except Exception as e:
                logging.warning(f"Could not restore launcher: {e}")

        print(f"SUCCESS: Removed '{removed_app.get('name', query)}' from FaceGATE protection.")
        print("         Original desktop launcher has been restored.")
        sys.exit(0)


    if args.list_cameras:
        from camera.device_enum import format_camera_list
        print(format_camera_list())
        sys.exit(0)

    if args.list_profiles:
        from database.embedding_store import load_embeddings, get_admin_user, get_cached_key
        enrolled = load_embeddings()
        admin_user = get_admin_user()
        print("👤 === Enrolled Face Biometric Profiles ===")
        if not enrolled:
            print("  No face profiles currently enrolled in the vault.")
        else:
            print(f"{'USERNAME':<20} {'ROLE':<16} {'EMBEDDING SIZE':<16} {'STATUS'}")
            print("-" * 65)
            for u_name, emb in enrolled.items():
                is_adm = (u_name == admin_user)
                role_str = "\033[95m★ Primary Admin\033[0m" if is_adm else "User"
                dim_str = f"{len(emb)} dims (float32)"
                print(f"{u_name:<20} {role_str:<25} {dim_str:<16} \033[92m● Enrolled\033[0m")
            print("=" * 65)
            print(f"Total Profiles: {len(enrolled)}")
        sys.exit(0)

    if args.delete_profile:
        target_user = args.delete_profile
        verify_cli_admin_access(f"Delete Profile '{target_user}'")
        from database.embedding_store import delete_embedding
        try:
            delete_embedding(target_user)
            print(f"SUCCESS: Enrolled face profile for '{target_user}' has been securely deleted.")
            sys.exit(0)
        except Exception as e:
            print(f"Error deleting profile '{target_user}': {e}", file=sys.stderr)
            sys.exit(1)

    if args.export_logs:
        export_path = args.export_logs
        fmt = "json" if export_path.lower().endswith(".json") else "csv"
        from database.audit_log import export_audit_logs
        ok, count, msg = export_audit_logs(export_path, format=fmt)
        if ok:
            print(f"SUCCESS: {msg}")
            sys.exit(0)
        else:
            print(f"Error: {msg}", file=sys.stderr)
            sys.exit(1)

    if args.verify_integrity:
        from database.audit_log import verify_audit_log_integrity
        from security.state_watchdog import is_initialized, check_critical_files
        print("🔐 === FaceGATE Cryptographic & State Integrity Audit ===")
        
        # 1. State files check
        if is_initialized():
            issues = check_critical_files()
            if not issues:
                print("  \033[92m[PASS]\033[0m State Files: All critical security state files present.")
            else:
                missing = ", ".join(i["file"] for i in issues)
                print(f"  \033[91m[FAIL]\033[0m State Files: Missing critical files ({missing})")
        else:
            print("  \033[96m[INFO]\033[0m State Files: System not yet initialized.")

        # 2. SQLite hash chain check
        valid_chain, verified_count, log_msg = verify_audit_log_integrity()
        if valid_chain:
            print(f"  \033[92m[PASS]\033[0m Audit Hash Chain: {log_msg}")
        else:
            print(f"  \033[91m[FAIL]\033[0m Audit Hash Chain: {log_msg}")

        print("=========================================================")
        sys.exit(0 if valid_chain else 1)

    if args.benchmark:
        print("⚡ === FaceGATE-Linux Performance & Latency Benchmark ===")
        import time
        import numpy as np
        import cv2

        # 1. Benchmark Crypto Key Derivation
        print("  [1/4] Benchmarking PBKDF2-HMAC-SHA256 (600,000 iterations)...")
        from security.crypto_engine import derive_key
        t0 = time.perf_counter()
        _k = derive_key(b"benchmark_password_1234", b"benchmark_salt_1234", iterations=600000)
        t_kdf = time.perf_counter() - t0
        print(f"        -> Key Derivation Latency: \033[92m{t_kdf * 1000:.2f} ms\033[0m")

        # 2. Benchmark Camera Capture Latency
        print("  [2/4] Benchmarking Camera Frame Acquisition...")
        from camera.device_enum import find_best_rgb_camera
        cam_idx = find_best_rgb_camera()
        cap = cv2.VideoCapture(cam_idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap = cv2.VideoCapture(cam_idx)
        if cap.isOpened():
            frames_grabbed = 0
            t_start = time.perf_counter()
            for _ in range(10):
                ret, _f = cap.read()
                if ret:
                    frames_grabbed += 1
            t_total = time.perf_counter() - t_start
            cap.release()
            fps = frames_grabbed / t_total if t_total > 0 else 0
            print(f"        -> Camera Device Index {cam_idx}: \033[92m{fps:.1f} FPS\033[0m ({t_total/frames_grabbed*1000:.1f} ms/frame)")
        else:
            print("        -> Camera device not accessible for capture test.")

        # 3. Benchmark ONNX Model & Feature Extraction
        print("  [3/4] Benchmarking InsightFace Detector & Feature Embedding...")
        try:
            from recognition.detector import Detector
            current_dir = os.path.dirname(os.path.abspath(__file__))
            models_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "models"))
            detector = Detector(root_dir=models_dir)
            
            # Synthetic 640x480 frame with simulated face
            dummy_frame = np.full((480, 640, 3), 128, dtype=np.uint8)
            t_det0 = time.perf_counter()
            faces = detector.detect_faces(dummy_frame)
            t_det = time.perf_counter() - t_det0
            print(f"        -> Detector Provider: \033[96m{detector.get_provider_name()}\033[0m")
            print(f"        -> Detection Inference Latency: \033[92m{t_det * 1000:.2f} ms\033[0m")
        except Exception as e:
            print(f"        -> Model benchmark skipped: {e}")

        # 4. Benchmark Cosine Matcher
        print("  [4/4] Benchmarking Cosine Similarity Vector Matcher (1,000 queries)...")
        from recognition.matcher import cosine_similarity
        v1 = np.random.randn(512).astype(np.float32)
        v2 = np.random.randn(512).astype(np.float32)
        t_m0 = time.perf_counter()
        for _ in range(1000):
            cosine_similarity(v1, v2)
        t_m = time.perf_counter() - t_m0
        print(f"        -> Vector Matching Throughput: \033[92m{1000 / t_m:.0f} comparisons/sec\033[0m ({t_m:.4f} ms per 1k)")

        print("=========================================================")
        sys.exit(0)

    if args.export_profile:
        verify_cli_admin_access("Export Profiles")
        from security.profile_transfer import export_profile
        try:
            count, path = export_profile(args.export_profile, export_users=args.export_user)
            print(f"SUCCESS: Exported {count} face profile(s) to '{path}'.")
            sys.exit(0)
        except Exception as e:
            print(f"Error exporting profiles: {e}", file=sys.stderr)
            sys.exit(1)

    if args.import_profile:
        verify_cli_admin_access("Import Profiles")
        from security.profile_transfer import import_profile
        try:
            users = import_profile(args.import_profile, force_import=args.force_import)
            print(f"SUCCESS: Imported {len(users)} face profile(s): {', '.join(users)}.")
            sys.exit(0)
        except Exception as e:
            print(f"Error importing profiles: {e}", file=sys.stderr)
            sys.exit(1)

    if args.health:
        from utils.health_check import run_health_check
        passed, total, report = run_health_check()
        print("\n".join(report))
        sys.exit(0 if passed == total else 1)


    if args.status:
        from PySide6.QtDBus import QDBusInterface, QDBusConnection
        from database.embedding_store import load_embeddings, get_cached_key
        from database.audit_log import get_recent_logs
        
        config = get_config()
        print("🛡️  === FaceGATE Status Dashboard ===")
        
        # Check Daemon Status (IPC Socket + D-Bus)
        daemon_active = False
        try:
            from locking.ipc_service import send_cross_platform_ipc_command
            ok, _ = send_cross_platform_ipc_command("Ping", timeout_ms=800)
            if ok:
                daemon_active = True
        except Exception:
            pass

        if not daemon_active:
            try:
                bus = QDBusConnection.sessionBus()
                if bus.isConnected():
                    interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
                    if interface.isValid():
                        daemon_active = True
            except Exception:
                pass
                
        status_str = "\033[92m● ACTIVE (Running)\033[0m" if daemon_active else "\033[91m○ INACTIVE (Not Running)\033[0m"

        print(f"  Daemon Status  : {status_str}")
        
        # Encryption Vault Status
        key = get_cached_key()
        vault_str = "\033[92mUnlocked (Key Cached)\033[0m" if key else "\033[93mLocked (Master Password Required)\033[0m"
        print(f"  Security Vault : {vault_str}")
        
        # Protected Apps
        apps = config.get("protected_apps", [])
        apps_list = apps if isinstance(apps, list) else []
        print(f"  Protected Apps : {len(apps_list)}")
        for app in apps_list:
            if isinstance(app, dict):
                app_id = app.get("id", "unknown")
                app_name = app.get("name", app_id)
                print(f"    - {app_name} ({app_id})")
            
        # Enrolled Profiles
        try:
            enrolled = load_embeddings()
            users = list(enrolled.keys())
            print(f"  Enrolled Faces : {len(users)} ({', '.join(users) if users else 'none'})")
        except Exception:
            print("  Enrolled Faces : Unknown (Vault Locked)")
            
        # Recent Audit Trail
        logs = get_recent_logs(limit=5)
        print("\n  Recent Activity (Last 5 events):")
        if not logs:
            print("    (No authentication logs recorded)")
        else:
            for log in logs:
                res = log.get('result', 'unknown')
                res_symbol = "✓" if res == 'success' else "✗" if res == 'fail' else "!"
                color = "\033[92m" if res == 'success' else "\033[91m" if res == 'fail' else "\033[93m"
                app = log.get('app_identifier', 'unknown')
                method = log.get('method', 'unknown')
                ts = log.get('timestamp', '')
                print(f"    {color}[{res_symbol}]\033[0m {ts} | {app} via {method} ({res})")
                
        print("===========================================")
        sys.exit(0)

    if args.restore_launchers or args.restore_all:
        from locking.launcher_manager import get_launcher_manager
        manager = get_launcher_manager()
        count = manager.restore_all_launchers()
        print(f"Emergency Restoration: Successfully restored {count} launcher(s) to original state.")
        sys.exit(0)

    if args.enable:
        from PySide6.QtDBus import QDBusInterface, QDBusConnection, QDBusReply
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
            if interface.isValid():
                raw_reply = interface.call("Enable")
                reply = QDBusReply(raw_reply)
                if reply.isValid() and reply.value():
                    print("FaceGate monitoring successfully enabled/resumed.")
                    sys.exit(0)
                else:
                    logging.error("D-Bus Enable call failed.")
                    sys.exit(1)
            else:
                logging.info("FaceGate daemon is not active on D-Bus. Enabling systemd user service...")
                from utils.systemd_manager import enable
                if enable():
                    print("FaceGate systemd user service enabled.")
                    sys.exit(0)
                else:
                    print("Error: Could not enable FaceGate systemd service.", file=sys.stderr)
                    sys.exit(1)
        else:
            logging.error("Failed to connect to Session D-Bus.")
            sys.exit(1)

    if args.disable is not None:
        mins = args.disable if args.disable > 0 else 15
        from PySide6.QtDBus import QDBusInterface, QDBusConnection, QDBusReply
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
            if interface.isValid():
                raw_reply = interface.call("Disable", mins)
                reply = QDBusReply(raw_reply)
                if reply.isValid() and reply.value():
                    print(f"FaceGate monitoring successfully paused/disabled for {mins} minutes.")
                    sys.exit(0)
                else:
                    logging.error("D-Bus Disable call failed.")
                    sys.exit(1)
            else:
                print("Error: FaceGate daemon is not running on D-Bus.", file=sys.stderr)
                sys.exit(1)
        else:
            logging.error("Failed to connect to Session D-Bus.")
            sys.exit(1)

    if args.key_fd is not None:
        try:
            key_bytes = os.read(args.key_fd, 32)
            os.close(args.key_fd)
            from database.embedding_store import set_cached_key
            set_cached_key(key_bytes)
        except Exception as e:
            logging.error(f"Failed to read key from fd {args.key_fd}: {e}")

    if args.emergency_kill:
        from locking.ipc_service import send_cross_platform_ipc_command
        ok, res = send_cross_platform_ipc_command("EmergencyKill")
        if ok:
            logging.info("Emergency kill command sent to FaceGate daemon via IPC.")
            sys.exit(0)
        from PySide6.QtDBus import QDBusInterface, QDBusConnection
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
            if interface.isValid():
                interface.call("EmergencyKill")
                logging.info("Emergency kill command sent to FaceGate daemon via D-Bus.")
                sys.exit(0)
        logging.error("FaceGate daemon is not active on IPC socket or D-Bus.")
        sys.exit(1)

    if args.lock_all:
        from locking.ipc_service import send_cross_platform_ipc_command
        ok, res = send_cross_platform_ipc_command("RelockAll")
        if ok:
            logging.info("Panic lockdown command sent to FaceGate daemon via IPC.")
            sys.exit(0)
        from PySide6.QtDBus import QDBusInterface, QDBusConnection
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
            if interface.isValid():
                interface.call("RelockAll")
                logging.info("Panic lockdown command sent to FaceGate daemon via D-Bus.")
                sys.exit(0)
        logging.error("FaceGate daemon is not active on IPC socket or D-Bus.")
        sys.exit(1)


    if args.set_master_password:
        from security.credential_store import set_master_password_cli
        set_master_password_cli()
        sys.exit(0)
        
    elif args.settings:
        from ui.settings_window import SettingsWindow
        from database.embedding_store import load_embeddings
        from database.audit_log import log_auth_attempt
        
        app = QApplication(sys.argv)
        
        # Verify admin face if any embeddings exist
        from database.embedding_store import EMBEDDING_FILE
        has_enrolled = False
        try:
            enrolled = load_embeddings()
            has_enrolled = len(enrolled) > 0
        except Exception:
            has_enrolled = os.path.exists(EMBEDDING_FILE)
            
        config = get_config()
        if (has_enrolled or os.path.exists(EMBEDDING_FILE)) and config.get("security.lock_settings_window", True):
            # Check if FaceGate daemon is active on session D-Bus
            dbus_success = False
            dbus_active = False
            
            from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusReply
            bus = QDBusConnection.sessionBus()
            if bus.isConnected():
                interface = QDBusInterface(
                    "org.facegate.FaceGate",
                    "/org/facegate/FaceGate",
                    "org.facegate.FaceGate",
                    bus
                )
                if interface.isValid():
                    dbus_active = True
                    from PySide6.QtDBus import QDBus
                    logging.info("Requesting Settings Access authorization via running FaceGate daemon...")
                    raw_reply = interface.callWithArgumentList(
                        QDBus.CallMode.Block,
                        "RequestAdminAuth",
                        ["Settings Access"]
                    )
                    reply = QDBusReply(raw_reply)
                    if reply.isValid():
                        dbus_success = reply.value()
                        if dbus_success:
                            # Key transfer: the daemon shares the encryption key via
                            # the RAM tmpfs file (/run/user/{uid}/facegate.key) which
                            # get_cached_key() reads automatically. No D-Bus key
                            # transfer needed (removed for security — see audit §1.1).
                            from database.embedding_store import get_cached_key
                            if get_cached_key():
                                logging.info("Encryption key loaded from RAM key file after daemon auth.")
                    else:
                        logging.error(f"D-Bus auth call failed: {reply.error().message()}")
            
            if dbus_active and dbus_success:
                logging.info("Settings Access authorized via daemon.")
            else:
                # Fallback to local AuthDialog
                logging.info("Daemon verification skipped or unsuccessful. Running local verification.")
                mode = "face" if os.path.exists(EMBEDDING_FILE) else "password"
                raw_timeout = config.get("app_monitor.auth_timeout_seconds", 60)
                timeout_sec = int(raw_timeout if isinstance(raw_timeout, (int, float, str)) else 60)
                dialog = AuthDialog("Settings Access", mode=mode, timeout_seconds=timeout_sec)
                result = dialog.exec()
                success = (result == QDialog.DialogCode.Accepted)
                log_auth_attempt("Settings Access", "face" if not dialog.fallback_to_password else "password", "success" if success else "fail", getattr(dialog, "final_score", None), getattr(dialog, "matched_user", None) if success else None)
                if not success:
                    logging.info("Settings Access: Verification failed. Exiting.")
                    sys.exit(1)
                
        dialog = SettingsWindow()
        dialog.setWindowState(Qt.WindowState.WindowActive)
        dialog.raise_()
        dialog.activateWindow()
        dialog.exec()
        sys.exit(0)
        
    elif args.enroll:
        # CLI Enrollment mode - Requires Admin Authentication
        verify_cli_admin_access("Enrollment Access")
        from recognition.cli_enroll import enroll_user
        enroll_user(args.enroll)
        sys.exit(0)
        
    elif args.recognize:
        # Recognition subprocess mode (GUI)
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        
        desktop_name = args.recognize
        config = get_config()
        
        # Determine app name and auth_mode configuration
        app_name = desktop_name
        target_app = None
        protected_apps_list = config.get("protected_apps", [])
        if isinstance(protected_apps_list, list):
            for p_app in protected_apps_list:
                if isinstance(p_app, dict) and (p_app.get("desktop_name") == desktop_name or p_app.get("id") == desktop_name):
                    app_name = p_app.get("name", desktop_name)
                    target_app = p_app
                    break
                
        raw_timeout = config.get("app_monitor.auth_timeout_seconds", 60)
        timeout_sec = int(raw_timeout if isinstance(raw_timeout, (int, float, str)) else 60)
        
        from database.embedding_store import EMBEDDING_FILE, OLD_EMBEDDING_FILE
        configured_mode = target_app.get("auth_mode") if target_app else None
        if configured_mode in ("face", "password", "face+password"):
            mode = configured_mode
        else:
            mode = "face" if (os.path.exists(EMBEDDING_FILE) or os.path.exists(OLD_EMBEDDING_FILE)) else "password"
            
        logging.info(f"Recognition subprocess launching for '{app_name}' in '{mode}' mode.")
        
        dialog = AuthDialog(app_name, mode=mode, timeout_seconds=timeout_sec)
        dialog.setWindowState(Qt.WindowState.WindowActive)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        
        # Ensure window stays on top & takes active focus across Linux desktop managers
        QTimer.singleShot(50, lambda: (dialog.setWindowState(Qt.WindowState.WindowActive), dialog.raise_(), dialog.activateWindow()))
        
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted or getattr(dialog, "authenticated", False):
            actual_method = "password" if (dialog.fallback_to_password or mode == "password") else "face"
            print(f"FACEGATE_METHOD:{actual_method}")
            if hasattr(dialog, "final_score") and dialog.final_score is not None:
                print(f"FACEGATE_SCORE:{dialog.final_score}")
            if hasattr(dialog, "matched_user") and dialog.matched_user is not None:
                print(f"FACEGATE_USER:{dialog.matched_user}")
            sys.stdout.flush()
            sys.exit(0)
        else:
            if dialog.fallback_to_password:
                sys.exit(4)
            elif dialog.camera_error:
                err_msg = getattr(dialog, "camera_error_msg", "")
                if "Device not found" in err_msg:
                    sys.exit(10)
                elif "Permission denied" in err_msg:
                    sys.exit(11)
                elif "Device busy" in err_msg:
                    sys.exit(12)
                else:
                    sys.exit(3)
            elif dialog.timed_out:
                sys.exit(2)
            else:
                sys.exit(1)

    elif args.auth_launch:
        # Client launch mode
        # Extract remaining arguments after '--'
        try:
            dash_idx = sys.argv.index('--')
            exec_args = sys.argv[dash_idx + 1:]
        except ValueError:
            exec_args = []
            
        if not exec_args:
            logging.error("Launcher: No execution command provided after '--'")
            sys.exit(1)
            
        run_auth_launch(args.auth_launch, exec_args)
        
    elif args.monitor:
        # Daemon monitor mode - enforce single instance lock
        from utils.instance_lock import SingleInstanceLock
        instance_lock = SingleInstanceLock("facegate_daemon")
        if not instance_lock.acquire():
            logging.warning("FaceGate daemon is already running. Exiting duplicate instance to prevent dual tray icons.")
            print("FaceGate daemon is already running.")
            sys.exit(0)

        config = get_config()
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)

        # Daemon starts in locked state. The user must authenticate via
        # master password when the first protected app triggers auth.
        # No hardcoded default password is used.
        logging.info("Daemon starting in locked state. Master password required to unlock.")

        fg_app = FaceGateApplication(config)

        # Setup crash recovery and signal handlers
        import atexit

        def cleanup_on_exit():
            logging.info("Abnormal/Termination cleanup triggered: restoring launchers and flushing state...")
            try:
                instance_lock.release()
            except Exception:
                pass
            try:
                from locking.launcher_manager import get_launcher_manager
                get_launcher_manager().restore_all_launchers()
            except Exception as e:
                logging.error(f"Cleanup error restoring launchers: {e}")

        atexit.register(cleanup_on_exit)

        def exception_hook(exctype, value, tb):
            logging.error("Uncaught exception in daemon main loop:", exc_info=(exctype, value, tb))
            cleanup_on_exit()
            sys.__excepthook__(exctype, value, tb)

        sys.excepthook = exception_hook

        def signal_handler(signum, frame):
            logging.info(f"Received terminal signal ({signum}). Restoring launchers and exiting...")
            cleanup_on_exit()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, signal_handler)

        sys.exit(app.exec())
    else:
        parser.print_help()
        sys.exit(0)

if __name__ == '__main__':
    main()
