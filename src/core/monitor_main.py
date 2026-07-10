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

class FaceGateApplication(QObject):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.active = True
        self.disabled_until = None
        self.authorized_apps = {}  # app_id -> bool
        self.auth_timestamps = {}  # app_id -> float (timestamp)
        
        # Initialize authorized state for all protected apps as False
        for app in self.get_protected_apps():
            self.authorized_apps[app["id"]] = False

        # Timer for handling disabled duration auto-resumption
        self.disabled_timer = QTimer(self)
        self.disabled_timer.setSingleShot(True)
        self.disabled_timer.timeout.connect(self.resume)

        # Setup periodic recheck of desktop launcher shadowing
        recheck_interval = int(self.config.get("behavior.launcher_recheck_interval_minutes", 10))
        if recheck_interval > 0:
            self.recheck_timer = QTimer(self)
            self.recheck_timer.timeout.connect(self.recheck_launcher_shadowing)
            self.recheck_timer.start(recheck_interval * 60 * 1000)

        # Setup AppMonitor
        poll_interval = float(self.config.get("app_monitor.poll_interval_seconds", 1.5))
        self.monitor = AppMonitor(self, poll_interval=poll_interval)
        self.monitor.signals.request_auth.connect(self.handle_monitor_auth)

        # D-Bus sleep & lock monitors for preventing trespassing
        from PySide6.QtDBus import QDBusConnection
        
        # Connect to systemd-logind PrepareForSleep signal on system bus
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
            
        # Connect to GNOME Screensaver ActiveChanged signal on session bus
        session_bus = QDBusConnection.sessionBus()
        if session_bus.isConnected():
            session_bus.connect(
                "org.gnome.ScreenSaver",
                "/org/gnome/ScreenSaver",
                "org.gnome.ScreenSaver",
                "ActiveChanged",
                self, "handle_screensaver_active_changed"
            )
            logging.info("Connected to GNOME ScreenSaver ActiveChanged D-Bus signal.")

        # Register D-Bus Service
        self.dbus_service = FaceGateService(self)
        if not register_dbus_service(self.dbus_service):
            logging.error("Could not start FaceGate D-Bus service. Exiting.")
            sys.exit(1)

        # Launcher Substitution
        logging.info("Applying launcher substitutions...")
        apply_substitution(self.get_protected_apps())

        # Start process monitor
        self.monitor.start()

        # Try to initialize Tray Icon (with retry loop for desktop env startup races)
        self.tray = None
        self.check_tray_and_start(attempts=0)

    def get_protected_apps(self):
        return self.config.get("protected_apps", [])

    def is_active(self) -> bool:
        return self.active

    def is_app_authorized(self, app_id: str) -> bool:
        return self.authorized_apps.get(app_id, False)

    def get_app_id_from_desktop(self, desktop_name: str) -> str:
        for app in self.get_protected_apps():
            if app.get("desktop_name") == desktop_name:
                return app.get("id")
        return desktop_name

    def get_app_name(self, identifier: str) -> str:
        for app in self.get_protected_apps():
            if app.get("id") == identifier or app.get("desktop_name") == identifier:
                return app.get("name", identifier)
        return identifier

    def authorize_app(self, app_identifier: str):
        app_id = self.get_app_id_from_desktop(app_identifier)
        was_authorized = self.authorized_apps.get(app_id, False)
        self.authorized_apps[app_id] = True
        self.auth_timestamps[app_id] = time.time()
        logging.info(f"State updated: Application '{app_id}' is UNLOCKED.")
        from PySide6.QtWidgets import QSystemTrayIcon
        if not was_authorized and self.config.get("behavior.notify_on_auth", True) and self.tray:
            app_name = self.get_app_name(app_id)
            self.tray.showMessage("Application Unlocked", f"Access to '{app_name}' has been authorized.", QSystemTrayIcon.MessageIcon.Information, 3000)

    def relock_app(self, app_id: str):
        was_authorized = self.authorized_apps.get(app_id, False)
        self.authorized_apps[app_id] = False
        logging.info(f"State updated: Application '{app_id}' is LOCKED.")
        # Force monitor to recheck active PIDs for this app if it is running
        self.monitor.clear_seen_pids()
        from PySide6.QtWidgets import QSystemTrayIcon
        if was_authorized and self.config.get("behavior.notify_on_auth", True) and self.tray:
            app_name = self.get_app_name(app_id)
            self.tray.showMessage("Application Locked", f"Access to '{app_name}' has been re-locked.", QSystemTrayIcon.MessageIcon.Information, 3000)

    @Slot()
    def relock_all(self):
        for app in self.get_protected_apps():
            self.relock_app(app["id"])

    @Slot(bool)
    def handle_prepare_for_sleep(self, starting_sleep: bool):
        if starting_sleep:
            if self.config.get("behavior.lock_on_sleep_or_lock", True):
                logging.info("System preparing for sleep/suspend. Relocking all applications to prevent trespassing.")
                self.relock_all()

    @Slot(bool)
    def handle_screensaver_active_changed(self, active: bool):
        if active:
            if self.config.get("behavior.lock_on_sleep_or_lock", True):
                logging.info("Screensaver/Lock screen activated. Relocking all applications to prevent trespassing.")
                self.relock_all()

    def recheck_launcher_shadowing(self):
        from locking.launcher_sub import check_and_fix_substitutions
        check_and_fix_substitutions(self.get_protected_apps())
        logging.info("All applications re-locked.")

    @Slot()
    def resume(self):
        self.disabled_timer.stop()
        self.disabled_until = None
        self.active = True
        self.monitor.clear_seen_pids()
        if self.tray:
            self.tray.update_tray_state()
        logging.info("FaceGate monitor is now ACTIVE.")

    def verify_admin_face(self, reason: str) -> bool:
        """
        Authenticates using face recognition.
        If there are no enrolled faces (first setup), returns True immediately.
        """
        from database.embedding_store import load_embeddings
        try:
            enrolled = load_embeddings()
        except Exception:
            enrolled = {}
            
        if not enrolled:
            logging.info("Admin verification: No enrolled faces found. Bypassing check.")
            return True
            
        from ui.auth_dialog import AuthDialog
        timeout_sec = self.config.get("app_monitor.auth_timeout_seconds", 60)
        dialog = AuthDialog(reason, mode="face", timeout_seconds=timeout_sec)
        result = dialog.exec()
        
        success = (result == QDialog.DialogCode.Accepted)
        
        from database.audit_log import log_auth_attempt
        log_auth_attempt(reason, "face" if not dialog.fallback_to_password else "password", "success" if success else "fail", getattr(dialog, "final_score", None), getattr(dialog, "matched_user", None) if success else None)
        
        return success

    def disable_for(self, minutes: int):
        if not self.verify_admin_face("Disable FaceGate"):
            logging.warning("Disable FaceGate: Verification failed.")
            return
            
        self.disabled_until = time.time() + (minutes * 60)
        self.active = False
        self.disabled_timer.start(minutes * 60 * 1000)
        if self.tray:
            self.tray.update_tray_state()
        logging.info(f"FaceGate monitor PAUSED for {minutes} minutes.")

    def get_remaining_disabled_seconds(self) -> float:
        if self.disabled_until:
            return max(0.0, self.disabled_until - time.time())
        return 0.0

    def check_tray_and_start(self, attempts: int):
        if QSystemTrayIcon.isSystemTrayAvailable():
            logging.info("System tray is available. Initializing Tray Icon.")
            self.tray = FaceGateTray(self)
            self.tray.show()
        elif attempts < 20:  # 20 * 500ms = 10s
            logging.info(f"System tray not available yet. Retrying in 500ms... (Attempt {attempts + 1}/20)")
            QTimer.singleShot(500, lambda: self.check_tray_and_start(attempts + 1))
        else:
            logging.error("System tray could not be initialized after 10s. Running in headless mode.")

    @Slot(str, int)
    def handle_monitor_auth(self, desktop_name: str, pid: int):
        """Triggered when background thread suspends a protected process."""
        logging.info(f"Handling AppMonitor suspension for '{desktop_name}' (PID: {pid})")
        
        try:
            import psutil
            if not psutil.pid_exists(pid):
                logging.warning(f"Process PID {pid} died before auth was shown.")
                return

            from database.embedding_store import get_cached_key
            cached_key = get_cached_key()
            
            if not cached_key:
                logging.info("Daemon is locked (backstop). Displaying GUI password prompt directly in daemon.")
                app_name = self.get_app_name(desktop_name)
                dialog = AuthDialog(app_name, mode="password")
                res = dialog.exec()
                success = (res == AuthDialog.DialogCode.Accepted)
                
                from database.audit_log import log_auth_attempt
                log_auth_attempt(desktop_name, "password", "success" if success else "fail", None, getattr(dialog, "matched_user", None) if success else None)
                
                if success:
                    self.authorize_app(desktop_name)
                    try:
                        p = psutil.Process(pid)
                        p.resume()
                        logging.info(f"AppMonitor: Resumed process '{desktop_name}' (PID: {pid}) after successful authentication.")
                    except Exception as ex:
                        logging.error(f"Failed to resume process: {ex}")
                else:
                    try:
                        p = psutil.Process(pid)
                        p.kill()
                        logging.info(f"AppMonitor: Killed process '{desktop_name}' (PID: {pid}) due to authentication failure.")
                    except Exception as ex:
                        logging.error(f"Failed to kill process: {ex}")
                return

            from locking.launcher_sub import get_facegate_executable
            facegate_bin = get_facegate_executable()
            
            import subprocess
            import os
            
            cmd = [facegate_bin, "--recognize", desktop_name]
            pass_fds = []
            r, w = os.pipe()
            os.set_inheritable(r, True)
            cmd.extend(["--key-fd", str(r)])
            pass_fds.append(r)
                
            logging.info(f"Spawning recognition subprocess for backstop: {facegate_bin} --recognize {desktop_name} (Pipe security enabled)")
            
            # Start the subprocess asynchronously so we can poll the PID and check if it is still alive!
            # If the target process is killed while we wait, we terminate the subprocess.
            proc = subprocess.Popen(cmd, pass_fds=pass_fds, stdout=subprocess.PIPE, text=True)
            
            os.close(r)
            try:
                os.write(w, cached_key)
            finally:
                os.close(w)
            
            # Watchdog timer to kill subprocess if target PID exits
            watch_timer = QTimer(self)
            def check_process_alive():
                # Check if target process was terminated
                if not psutil.pid_exists(pid):
                    logging.info(f"Target process PID {pid} died externally. Terminating recognition subprocess.")
                    proc.terminate()
                    watch_timer.stop()
                # Check if subprocess finished
                elif proc.poll() is not None:
                    watch_timer.stop()
            
            watch_timer.timeout.connect(check_process_alive)
            watch_timer.start(100) # Check every 100ms
            
            # Wait for subprocess while keeping Qt event loop alive
            while proc.poll() is None:
                QApplication.processEvents()
                import time
                time.sleep(0.05)

            stdout_data, _ = proc.communicate()
            exit_code = proc.returncode
            watch_timer.stop()
            
            logging.info(f"Backstop recognition subprocess exited with code {exit_code}")
            
            # Parse similarity score and user if present
            score = None
            matched_user = None
            if stdout_data:
                for line in stdout_data.splitlines():
                    if line.startswith("FACEGATE_SCORE:"):
                        try:
                            score = float(line.split(":")[1])
                        except ValueError:
                            pass
                    elif line.startswith("FACEGATE_USER:"):
                        matched_user = line.split(":")[1]

            success = False
            method = "face"
            result = "fail"
            confidence = score
            username = None

            if exit_code == 0:
                success = True
                result = "success"
                username = matched_user
            elif exit_code == 2:
                result = "timeout"
            elif exit_code in (3, 4):
                # Fallback to daemon password dialog
                logging.info(f"Backstop subprocess returned exit code {exit_code}. Displaying password fallback.")
                app_name = self.get_app_name(desktop_name)
                timeout_sec = self.config.get("app_monitor.auth_timeout_seconds", 60)
                
                # Check if process is still alive before showing password dialog
                if psutil.pid_exists(pid):
                    dialog = AuthDialog(app_name, mode="password", timeout_seconds=timeout_sec)
                    
                    # Watchdog timer for password dialog
                    pwd_watch_timer = QTimer(self)
                    def check_pwd_process_alive():
                        if not psutil.pid_exists(pid):
                            logging.info(f"Target process PID {pid} died. Closing password dialog.")
                            dialog.reject()
                            pwd_watch_timer.stop()
                    pwd_watch_timer.timeout.connect(check_pwd_process_alive)
                    pwd_watch_timer.start(100)
                    
                    res = dialog.exec()
                    pwd_watch_timer.stop()
                    success = (res == QDialog.DialogCode.Accepted)
                    method = "password"
                    result = "success" if success else "fail"
                    confidence = None
                    username = getattr(dialog, "matched_user", None) if success else None
            else:
                result = "fail"

            # Write to SQLite audit log
            from database.audit_log import log_auth_attempt
            log_auth_attempt(desktop_name, method, result, confidence, username)
            
            if success:
                # Resume process
                os.kill(pid, signal.SIGCONT)
                logging.info(f"Resumed process (PID: {pid}) after successful authentication.")
                app_id = self.get_app_id_from_desktop(desktop_name)
                self.authorize_app(app_id)
            else:
                policy = self.config.get("app_monitor.on_auth_failure", "kill")
                if policy == "kill":
                    try:
                        os.kill(pid, signal.SIGKILL)
                        logging.info(f"Killed process (PID: {pid}) due to authentication failure.")
                    except ProcessLookupError:
                        pass
                else:
                    logging.info(f"Process (PID: {pid}) remains suspended according to policy '{policy}'.")
                    
        except Exception as e:
            logging.error(f"Error managing process lifecycle: {e}")

    def trigger_manual_auth(self, desktop_name: str):
        """Called when user clicks a locked app in the tray menu."""
        self.dbus_service.request_auth_internal(desktop_name)

    @Slot()
    def open_settings(self):
        """Opens the Settings Window after face verification."""
        if not self.verify_admin_face("Settings Access"):
            logging.warning("Settings Access: Verification failed.")
            return
            
        from ui.settings_window import SettingsWindow
        if not hasattr(self, "_settings_window") or self._settings_window is None:
            self._settings_window = SettingsWindow(self.config, parent=None)
            self._settings_window.finished.connect(self.cleanup_settings_window)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def cleanup_settings_window(self, result):
        self._settings_window = None

    @Slot()
    def quit_app(self, bypass_protection=False):
        logging.info("Quit requested. Performing restoration...")
        
        # Check uninstall protection
        if not bypass_protection:
            if self.config.get("behavior.uninstall_protection", True):
                logging.info("Uninstall protection is active. Prompting for master password...")
                from ui.auth_dialog import AuthDialog
                dialog = AuthDialog("FaceGate Shutdown", mode="password")
                res = dialog.exec()
                if res != QDialog.DialogCode.Accepted:
                    logging.info("Shutdown cancelled due to password verification failure.")
                    return
        
        # Restore launchers
        try:
            restore_substitution(self.get_protected_apps())
            logging.info("Launcher modifications reverted.")
        except Exception as e:
            logging.error(f"Error restoring launchers: {e}")

        # Stop background monitoring thread
        if self.monitor:
            self.monitor.stop()

        logging.info("Shutting down FaceGate event loop.")
        QApplication.quit()

def run_auth_launch(desktop_name: str, exec_args: list):
    """
    Substituted launcher client entrypoint.
    Queries the running FaceGate daemon via D-Bus session bus.
    If authenticated, spawns the actual application command.
    """
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtDBus import QDBusInterface, QDBusConnection, QDBusReply

    # Needs QCoreApplication to bind to D-Bus event loop
    app = QCoreApplication(sys.argv)

    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        logging.error("Launcher: Cannot connect to session D-Bus. Launch blocked.")
        sys.exit(1)

    interface = QDBusInterface(
        "org.facegate.FaceGate",
        "/org/facegate/FaceGate",
        "org.facegate.FaceGate",
        bus
    )

    if not interface.isValid():
        logging.error("Launcher: FaceGate daemon is not running on D-Bus. Launch blocked.")
        print("Error: FaceGate lock daemon is not running. Please start FaceGate.", file=sys.stderr)
        sys.exit(1)

    logging.info(f"Launcher: Requesting auth for app '{desktop_name}'...")
    raw_reply = interface.call("RequestAuth", desktop_name)
    reply = QDBusReply(raw_reply)

    if not reply.isValid():
        logging.error(f"Launcher: D-Bus method call failed: {reply.error().message()}")
        sys.exit(1)

    authorized = reply.value()
    if authorized:
        logging.info(f"Launcher: Auth succeeded. Executing: {exec_args}")
        try:
            # Launch original command without locking execution block
            subprocess.Popen(exec_args, close_fds=True)
            sys.exit(0)
        except Exception as e:
            logging.error(f"Launcher: Failed to execute {exec_args}: {e}")
            sys.exit(1)
    else:
        logging.warning("Launcher: Auth rejected. Process execution blocked.")
        sys.exit(0)

def main():
    setup_logging()
    logging.info("Starting FaceGate-Linux application wrapper.")

    # Fallback env variables for graphical execution compatibility (e.g. under systemd user manager)
    if "DISPLAY" not in os.environ:
        os.environ["DISPLAY"] = ":0"
        logging.info("DISPLAY environment variable not found. Defaulting to :0 for systemd compatibility.")
    if "XAUTHORITY" not in os.environ:
        os.environ["XAUTHORITY"] = os.path.expanduser("~/.Xauthority")
        logging.info("XAUTHORITY environment variable not found. Defaulting to ~/.Xauthority for systemd compatibility.")

    parser = argparse.ArgumentParser(description="FaceGate-Linux lock system")
    parser.add_argument("--monitor", action="store_true", help="Start the main lock daemon and tray icon")
    parser.add_argument("--auth-launch", type=str, help="Authenticate launcher request for target desktop")
    parser.add_argument("--enroll", type=str, help="Enroll a face embedding for the specified username")
    parser.add_argument("--recognize", type=str, help="Run the face recognition subprocess dialog for target desktop")
    parser.add_argument("--set-master-password", action="store_true", help="Set or change the master password")
    parser.add_argument("--key-fd", type=int, help="File descriptor to read the encryption key from")
    parser.add_argument("--emergency-kill", action="store_true", help="Send emergency kill signal to running daemon via D-Bus")
    parser.add_argument("--lock-all", action="store_true", help="Send lockdown signal to running daemon via D-Bus")
    parser.add_argument("--settings", action="store_true", help="Launch the Settings GUI window")
    
    args, unknown = parser.parse_known_args()

    if args.key_fd is not None:
        try:
            key_bytes = os.read(args.key_fd, 32)
            os.close(args.key_fd)
            from database.embedding_store import set_cached_key
            set_cached_key(key_bytes)
        except Exception as e:
            logging.error(f"Failed to read key from fd {args.key_fd}: {e}")

    if args.emergency_kill:
        from PySide6.QtDBus import QDBusInterface, QDBusConnection
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
            if interface.isValid():
                interface.call("EmergencyKill")
                logging.info("Emergency kill command sent to FaceGate daemon.")
                sys.exit(0)
            else:
                logging.error("FaceGate daemon D-Bus interface is not active.")
                sys.exit(1)
        else:
            logging.error("Failed to connect to Session D-Bus.")
            sys.exit(1)

    if args.lock_all:
        from PySide6.QtDBus import QDBusInterface, QDBusConnection
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            interface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
            if interface.isValid():
                interface.call("RelockAll")
                logging.info("Panic lockdown command sent to FaceGate daemon.")
                sys.exit(0)
            else:
                logging.error("FaceGate daemon D-Bus interface is not active.")
                sys.exit(1)
        else:
            logging.error("Failed to connect to Session D-Bus.")
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
        try:
            enrolled = load_embeddings()
        except Exception:
            enrolled = {}
            
        config = get_config()
        if enrolled and config.get("security.lock_settings_window", True):
            timeout_sec = config.get("app_monitor.auth_timeout_seconds", 60)
            dialog = AuthDialog("Settings Access", mode="face", timeout_seconds=timeout_sec)
            result = dialog.exec()
            success = (result == QDialog.DialogCode.Accepted)
            log_auth_attempt("Settings Access", "face" if not dialog.fallback_to_password else "password", "success" if success else "fail", getattr(dialog, "final_score", None), getattr(dialog, "matched_user", None) if success else None)
            if not success:
                logging.info("Settings Access: Verification failed. Exiting.")
                sys.exit(1)
                
        dialog = SettingsWindow()
        dialog.exec()
        sys.exit(0)
        
    elif args.enroll:
        # CLI Enrollment mode
        from recognition.cli_enroll import enroll_user
        enroll_user(args.enroll)
        sys.exit(0)
        
    elif args.recognize:
        # Recognition subprocess mode (GUI)
        from PySide6.QtWidgets import QDialog
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        
        desktop_name = args.recognize
        config = get_config()
        
        # Determine app name
        app_name = desktop_name
        for p_app in config.get("protected_apps", []):
            if p_app.get("desktop_name") == desktop_name or p_app.get("id") == desktop_name:
                app_name = p_app.get("name", desktop_name)
                break
                
        timeout_sec = config.get("app_monitor.auth_timeout_seconds", 60)
        
        # Run dialog in face-preview mode
        dialog = AuthDialog(app_name, mode="face", timeout_seconds=timeout_sec)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
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
        # Daemon monitor mode
        config = get_config()
        startup_delay = int(config.get("behavior.startup_delay_seconds", 0))
        if startup_delay > 0:
            logging.info(f"Daemon: Delaying startup by {startup_delay} seconds...")
            import time
            time.sleep(startup_delay)
            
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        
        # Auto-unlock daemon on startup
        from database.embedding_store import get_or_prompt_key
        get_or_prompt_key()
        
        fg_app = FaceGateApplication(config)

        # Setup graceful signal handlers
        def signal_handler(signum, frame):
            logging.info(f"Received terminal signal ({signum}). Queuing graceful exit.")
            QMetaObject.invokeMethod(fg_app, "quit_app", Qt.ConnectionType.QueuedConnection)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        sys.exit(app.exec())
    else:
        parser.print_help()
        sys.exit(0)

if __name__ == '__main__':
    main()
