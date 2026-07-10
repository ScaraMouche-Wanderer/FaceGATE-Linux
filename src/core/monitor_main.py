import os
import sys
import argparse
import logging
import signal
import time
import subprocess
from typing import Dict

from PySide6.QtWidgets import QApplication, QSystemTrayIcon
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
        
        # Initialize authorized state for all protected apps as False
        for app in self.get_protected_apps():
            self.authorized_apps[app["id"]] = False

        # Timer for handling disabled duration auto-resumption
        self.disabled_timer = QTimer(self)
        self.disabled_timer.setSingleShot(True)
        self.disabled_timer.timeout.connect(self.resume)

        # Setup AppMonitor
        poll_interval = float(self.config.get("app_monitor.poll_interval_seconds", 1.5))
        self.monitor = AppMonitor(self, poll_interval=poll_interval)
        self.monitor.signals.request_auth.connect(self.handle_monitor_auth)

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
        self.authorized_apps[app_id] = True
        logging.info(f"State updated: Application '{app_id}' is UNLOCKED.")

    def relock_app(self, app_id: str):
        self.authorized_apps[app_id] = False
        logging.info(f"State updated: Application '{app_id}' is LOCKED.")
        # Force monitor to recheck active PIDs for this app if it is running
        self.monitor.clear_seen_pids()

    @Slot()
    def relock_all(self):
        for app in self.get_protected_apps():
            self.relock_app(app["id"])
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

    def disable_for(self, minutes: int):
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

            # Resolve facegate path dynamically
            from locking.launcher_sub import get_facegate_executable
            facegate_bin = get_facegate_executable()
            
            import subprocess
            import os
            from database.embedding_store import get_cached_key
            cached_key = get_cached_key()
            
            cmd = [facegate_bin, "--recognize", desktop_name]
            pass_fds = []
            r, w = -1, -1
            if cached_key:
                r, w = os.pipe()
                os.set_inheritable(r, True)
                cmd.extend(["--key-fd", str(r)])
                pass_fds.append(r)
                
            logging.info(f"Spawning recognition subprocess for backstop: {facegate_bin} --recognize {desktop_name} (Pipe security enabled)")
            
            # Start the subprocess asynchronously so we can poll the PID and check if it is still alive!
            # If the target process is killed while we wait, we terminate the subprocess.
            proc = subprocess.Popen(cmd, pass_fds=pass_fds)
            
            if r != -1:
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
            
            # Wait for subprocess to finish
            exit_code = proc.wait()
            watch_timer.stop()
            
            logging.info(f"Backstop recognition subprocess exited with code {exit_code}")
            
            success = False
            if exit_code == 0:
                success = True
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
    def quit_app(self):
        logging.info("Quit requested. Performing restoration...")
        
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

    parser = argparse.ArgumentParser(description="FaceGate-Linux lock system")
    parser.add_argument("--monitor", action="store_true", help="Start the main lock daemon and tray icon")
    parser.add_argument("--auth-launch", type=str, help="Authenticate launcher request for target desktop")
    parser.add_argument("--enroll", type=str, help="Enroll a face embedding for the specified username")
    parser.add_argument("--recognize", type=str, help="Run the face recognition subprocess dialog for target desktop")
    parser.add_argument("--set-master-password", action="store_true", help="Set or change the master password")
    parser.add_argument("--key-fd", type=int, help="File descriptor to read the encryption key from")
    
    args, unknown = parser.parse_known_args()

    if args.key_fd is not None:
        try:
            key_bytes = os.read(args.key_fd, 32)
            os.close(args.key_fd)
            from database.embedding_store import set_cached_key
            set_cached_key(key_bytes)
        except Exception as e:
            logging.error(f"Failed to read key from fd {args.key_fd}: {e}")

    if args.set_master_password:
        from security.credential_store import set_master_password_cli
        set_master_password_cli()
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
            sys.exit(0)
        else:
            if dialog.fallback_to_password:
                sys.exit(4)
            elif dialog.camera_error:
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
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        
        config = get_config()
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
