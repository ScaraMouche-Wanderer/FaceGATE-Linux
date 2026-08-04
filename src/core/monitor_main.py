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

        # Serialization state for handle_monitor_auth. See _process_auth_queue().
        self._auth_queue = []
        self._auth_busy = False
        
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
        self.monitor.signals.request_auth.connect(self.handle_monitor_auth, Qt.ConnectionType.QueuedConnection)

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
            
        # Connect to GNOME, KDE, and Xfce Screensaver signals on session bus
        session_bus = QDBusConnection.sessionBus()
        if session_bus.isConnected():
            # GNOME ScreenSaver
            session_bus.connect(
                "org.gnome.ScreenSaver",
                "/org/gnome/ScreenSaver",
                "org.gnome.ScreenSaver",
                "ActiveChanged",
                self, "handle_screensaver_active_changed"
            )
            # KDE / FreeDesktop ScreenSaver
            session_bus.connect(
                "org.freedesktop.ScreenSaver",
                "/ScreenSaver",
                "org.freedesktop.ScreenSaver",
                "ActiveChanged",
                self, "handle_screensaver_active_changed"
            )
            # Xfce ScreenSaver
            session_bus.connect(
                "org.xfce.ScreenSaver",
                "/org/xfce/ScreenSaver",
                "org.xfce.ScreenSaver",
                "ActiveChanged",
                self, "handle_screensaver_active_changed"
            )
            logging.info("Connected to ScreenSaver ActiveChanged D-Bus signals (GNOME/KDE/Xfce).")

        # Register D-Bus Service
        self.dbus_service = FaceGateService(self)
        if not register_dbus_service(self.dbus_service):
            logging.error("Could not start FaceGate D-Bus service. Exiting.")
            sys.exit(1)

        # Startup Recovery Check & Consistency Verification
        from locking.launcher_manager import get_launcher_manager
        get_launcher_manager().startup_recovery(self.get_protected_apps())

        # Startup Consistency Check & Launcher Substitution
        if self.is_active():
            logging.info("FaceGate daemon starting in ACTIVE mode. Applying launcher substitutions...")
            apply_substitution(self.get_protected_apps())
            self.monitor.start()
        else:
            logging.info("FaceGate daemon starting in INACTIVE mode. Restoring launchers...")
            restore_substitution(self.get_protected_apps())

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
    def reload_config(self) -> bool:
        """Hot-reloads configuration settings live without restarting the application or daemon."""
        try:
            self.config.reload()
            apply_substitution(self.get_protected_apps())
            poll_interval = float(self.config.get("app_monitor.poll_interval_seconds", 1.5))
            if hasattr(self, 'monitor') and self.monitor:
                self.monitor.poll_interval = poll_interval
                self.monitor.clear_seen_pids()
            if hasattr(self, 'tray') and self.tray:
                self.tray.refresh_icon_style()
            logging.info("FaceGateApplication: Configuration hot-reloaded successfully live.")
            return True
        except Exception as e:
            logging.error(f"Error hot-reloading configuration: {e}")
            return False

    @Slot()
    def resume(self):
        self.disabled_timer.stop()
        self.disabled_until = None
        self.active = True

        # Re-apply launcher substitutions on resume
        try:
            apply_substitution(self.get_protected_apps())
            logging.info("Re-applied launcher substitutions on resume.")
        except Exception as e:
            logging.error(f"Error re-applying launcher substitutions on resume: {e}")

        if hasattr(self, 'monitor') and self.monitor:
            self.monitor.clear_seen_pids()
            if not self.monitor.isRunning():
                self.monitor.start()

        if self.tray:
            self.tray.update_tray_state()
        logging.info("FaceGate monitor is now ACTIVE.")

    def _run_recognition_subprocess(self, reason: str) -> tuple[bool, str, float, str]:
        """Spawns the isolated recognition subprocess for admin face verification."""
        from database.embedding_store import get_cached_key, set_cached_key
        from locking.ipc_service import run_recognition_helper
        cached_key = get_cached_key()

        exit_code, stdout_data = run_recognition_helper(reason, cached_key)
        success = (exit_code == 0)

        actual_method = "face"
        score = None
        matched_user = None
        if stdout_data:
            for line in stdout_data.splitlines():
                line = line.strip()
                if line.startswith("FACEGATE_METHOD:"):
                    actual_method = line.split(":")[1]
                elif line.startswith("FACEGATE_SCORE:"):
                    try:
                        score = float(line.split(":")[1])
                    except ValueError:
                        pass
                elif line.startswith("FACEGATE_USER:"):
                    matched_user = line.split(":")[1]
                elif len(line) == 64 and all(c in "0123456789abcdefABCDEF" for c in line):
                    try:
                        key_bytes = bytes.fromhex(line)
                        if len(key_bytes) == 32:
                            set_cached_key(key_bytes)
                            logging.info("Successfully cached key returned from recognition subprocess.")
                    except Exception as ex:
                        logging.error(f"Failed to parse key returned from subprocess: {ex}")

        method = actual_method
        return success, method, score, matched_user

    def verify_admin_face(self, reason: str) -> bool:
        """
        Authenticates using face recognition.
        If there are no enrolled faces (first setup), returns True immediately.
        """
        from security.lockout_manager import is_locked_out
        locked_out, remaining = is_locked_out(reason)
        if locked_out:
            logging.warning(f"Admin verification for '{reason}' REJECTED due to active lockout ({remaining}s remaining).")
            from database.audit_log import log_auth_attempt
            log_auth_attempt(reason, "lockout", "fail")
            return False

        from database.embedding_store import load_embeddings, EMBEDDING_FILE
        import os
        try:
            enrolled = load_embeddings()
        except Exception:
            enrolled = {}

        if not enrolled and not os.path.exists(EMBEDDING_FILE):
            logging.info("Admin verification: No enrolled faces found and no database exists. Bypassing check.")
            return True

        success, actual_method, score, matched_user = self._run_recognition_subprocess(reason)

        from database.audit_log import log_auth_attempt
        log_auth_attempt(reason, actual_method, "success" if success else "fail", score, matched_user)
        return success

    def disable_for(self, minutes: int):
        if not self.verify_admin_face("Disable FaceGate"):
            logging.warning("Disable FaceGate: Verification failed.")
            return

        self.disabled_until = time.time() + (minutes * 60)
        self.active = False
        self.disabled_timer.start(minutes * 60 * 1000)

        # 1. Restore all launchers BEFORE stopping monitor or DBus
        from locking.launcher_manager import get_launcher_manager
        try:
            get_launcher_manager().restore_all_launchers()
            logging.info("Restored all launchers before stopping monitor on disable.")
        except Exception as e:
            logging.error(f"Error restoring launchers on disable: {e}")

        # 2. Stop monitor
        if hasattr(self, 'monitor') and self.monitor:
            self.monitor.stop()

        # 3. Clear runtime locks and suspended process list
        self.authorized_apps.clear()
        self.auth_timestamps.clear()
        if hasattr(self, 'monitor') and self.monitor:
            self.monitor.clear_seen_pids()

        if self.tray:
            self.tray.update_tray_state()
        logging.info(f"FaceGate monitor PAUSED for {minutes} minutes.")

    def get_remaining_disabled_seconds(self) -> float:
        if self.disabled_until:
            return max(0.0, self.disabled_until - time.time())
        return 0.0

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

    @Slot(str, int)
    def handle_monitor_auth(self, desktop_name: str, pid: int):
        """Triggered when background thread suspends a protected process.

        IMPORTANT: this only enqueues the request. The actual work (spawning
        the recognition subprocess and pumping the event loop while we wait
        for it) happens in _process_auth_queue(), which guarantees only ONE
        auth flow is ever active at a time. Without this guard, launching a
        second protected app (or the same app twice) while an auth dialog was
        already in flight would re-enter handle_monitor_auth() from inside
        the processEvents() pump below, stacking up multiple concurrent
        recognition subprocesses (each loading the full face-recognition
        model into memory). That reentrant stacking is a primary cause of
        random app crashes and, under memory pressure, the OOM killer taking
        down unrelated session processes (perceived as a "sudden logout").
        """
        logging.info(f"Queuing auth request for '{desktop_name}' (PID: {pid})")
        self._auth_queue.append((desktop_name, pid))
        if not self._auth_busy:
            self._process_auth_queue()

    def _process_auth_queue(self):
        if not self._auth_queue:
            self._auth_busy = False
            return
        self._auth_busy = True
        desktop_name, pid = self._auth_queue.pop(0)
        try:
            self._process_auth_request(desktop_name, pid)
        finally:
            # Always continue draining the queue, even if this request raised.
            # Defer via singleShot(0, ...) instead of recursing directly so we
            # unwind the current call stack first.
            QTimer.singleShot(0, self._process_auth_queue)

    def _process_auth_request(self, desktop_name: str, pid: int):
        logging.info(f"Handling AppMonitor suspension for '{desktop_name}' (PID: {pid})")
        
        try:
            import psutil
            if not psutil.pid_exists(pid):
                logging.warning(f"Process PID {pid} died before auth was shown.")
                return

            from security.lockout_manager import is_locked_out
            locked_out, remaining = is_locked_out(desktop_name)
            if locked_out:
                logging.warning(f"Backstop recognition for '{desktop_name}' BLOCKED due to active brute-force lockout ({remaining}s remaining).")
                policy = self.config.get("app_monitor.on_auth_failure", "kill")
                if policy == "kill":
                    try:
                        os.kill(pid, signal.SIGKILL)
                        logging.info(f"Killed process (PID: {pid}) due to active brute-force lockout.")
                    except ProcessLookupError:
                        pass
                from database.audit_log import log_auth_attempt
                log_auth_attempt(desktop_name, "lockout", "fail")
                return

            from database.embedding_store import get_cached_key
            cached_key = get_cached_key()

            from locking.launcher_sub import get_facegate_cmd
            cmd = list(get_facegate_cmd())
            cmd.extend(["--recognize", desktop_name])
            pass_fds = []
            w = None
            
            if cached_key is not None:
                r, w = os.pipe()
                os.set_inheritable(r, True)
                cmd.extend(["--key-fd", str(r)])
                pass_fds.append(r)
                
            logging.info(f"Spawning recognition subprocess for backstop: {' '.join(cmd)}")
            
            # Start the subprocess asynchronously so we can poll the PID and check if it is still alive!
            # If the target process is killed while we wait, we terminate the subprocess.
            proc = subprocess.Popen(cmd, pass_fds=pass_fds, stdout=subprocess.PIPE, text=True, close_fds=True)
            
            if cached_key is not None:
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
                time.sleep(0.05)

            stdout_data, _ = proc.communicate()
            exit_code = proc.returncode
            watch_timer.stop()
            
            logging.info(f"Backstop recognition subprocess exited with code {exit_code}")
            
            # Parse similarity score, user, and method if present
            score = None
            matched_user = None
            returned_key = None
            actual_method = None
            if stdout_data:
                for line in stdout_data.splitlines():
                    line = line.strip()
                    if line.startswith("FACEGATE_SCORE:"):
                        try:
                            score = float(line.split(":")[1])
                        except ValueError:
                            pass
                    elif line.startswith("FACEGATE_USER:"):
                        matched_user = line.split(":")[1]
                    elif line.startswith("FACEGATE_METHOD:"):
                        actual_method = line.split(":")[1]
                    elif len(line) == 64 and all(c in "0123456789abcdefABCDEF" for c in line):
                        try:
                            returned_key = bytes.fromhex(line)
                        except Exception:
                            pass

            success = False
            method = "face"
            result = "fail"
            confidence = score
            username = None

            if exit_code == 0:
                success = True
                result = "success"
                username = matched_user
                if returned_key and len(returned_key) == 32:
                    from database.embedding_store import set_cached_key
                    set_cached_key(returned_key)
                    logging.info("Successfully cached key returned from backstop recognition subprocess.")
                if actual_method:
                    method = actual_method
                else:
                    method = "password" if (returned_key and len(returned_key) == 32) else "face"
            elif exit_code == 2:
                result = "timeout"
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
        self._settings_window.setWindowState(Qt.WindowState.WindowActive)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def cleanup_settings_window(self, result):
        self._settings_window = None

    @Slot()
    def open_enrollment(self):
        """Opens the Guided Enrollment Wizard after verification."""
        if not self.verify_admin_face("Enrollment Access"):
            logging.warning("Enrollment Access: Verification failed.")
            return

        # 3. Open Enrollment Wizard
        from ui.enrollment_wizard import EnrollmentWizard
        if not hasattr(self, "_enrollment_wizard") or self._enrollment_wizard is None:
            self._enrollment_wizard = EnrollmentWizard(parent=None)
            self._enrollment_wizard.finished.connect(self.cleanup_enrollment_wizard)
        self._enrollment_wizard.setWindowState(Qt.WindowState.WindowActive)
        self._enrollment_wizard.show()
        self._enrollment_wizard.raise_()
        self._enrollment_wizard.activateWindow()

    def cleanup_enrollment_wizard(self, result):
        self._enrollment_wizard = None

    @Slot()
    def quit_app(self, bypass_protection=False, restore_launchers=True):
        logging.info("Quit requested. Performing shutdown...")
        
        # Check uninstall protection
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
        
        # Restore launchers on any quit/shutdown so system returns to default pre-protection state
        try:
            restore_substitution(self.get_protected_apps())
            logging.info("Launcher modifications reverted on shutdown.")
        except Exception as e:
            logging.error(f"Error restoring launchers on shutdown: {e}")

        # Stop background monitoring thread
        if self.monitor:
            self.monitor.stop()

        # Securely zero the cached encryption key from memory
        from database.embedding_store import clear_cached_key
        clear_cached_key()

        logging.info("Shutting down FaceGate event loop.")
        QApplication.quit()

def run_auth_launch(desktop_name: str, exec_args: list):
    """
    Substituted launcher client entrypoint.
    Queries the running FaceGate daemon via D-Bus session bus.
    If authenticated, spawns the actual application command.
    If FaceGate daemon is disabled or inactive, falls back to direct execution.
    """
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtDBus import QDBusInterface, QDBusConnection, QDBusReply

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
        logging.warning(f"Launcher: FaceGate daemon is not active. Falling back to direct launch for '{desktop_name}'.")
        try:
            subprocess.Popen(exec_args, close_fds=True, start_new_session=True)
            # Restore launchers in background thread since daemon is not running
            import threading
            from locking.launcher_sub import emergency_restore_launchers
            threading.Thread(target=emergency_restore_launchers, daemon=True).start()
            sys.exit(0)
        except Exception as e:
            logging.error(f"Launcher fallback failed to execute {exec_args}: {e}")
            sys.exit(1)

    # Needs QCoreApplication to bind to D-Bus event loop
    app = QCoreApplication(sys.argv)

    interface = QDBusInterface(
        "org.facegate.FaceGate",
        "/org/facegate/FaceGate",
        "org.facegate.FaceGate",
        bus
    )

    if not interface.isValid():
        logging.warning(f"Launcher: Interface invalid. Falling back to direct launch for '{desktop_name}'.")
        try:
            subprocess.Popen(exec_args, close_fds=True, start_new_session=True)
            import threading
            from locking.launcher_sub import emergency_restore_launchers
            threading.Thread(target=emergency_restore_launchers, daemon=True).start()
            sys.exit(0)
        except Exception as e:
            sys.exit(1)

    logging.info(f"Launcher: Requesting auth for app '{desktop_name}'...")
    from PySide6.QtDBus import QDBus
    raw_reply = interface.callWithArgumentList(
        QDBus.CallMode.Block,
        "RequestAuth",
        [desktop_name],
        300000  # 5-minute timeout so authentication dialog won't time out prematurely
    )
    reply = QDBusReply(raw_reply)

    if not reply.isValid():
        logging.error(f"Launcher: D-Bus method call failed ({reply.error().message()}). Blocking execution for security.")
        sys.exit(1)

    authorized = reply.value()
    if authorized:
        logging.info(f"Launcher: Auth succeeded. Executing: {exec_args}")
        try:
            subprocess.Popen(exec_args, close_fds=True, start_new_session=True)
            sys.exit(0)
        except Exception as e:
            logging.error(f"Launcher: Failed to execute {exec_args}: {e}")
            sys.exit(1)
    else:
        logging.warning("Launcher: Auth rejected. Process execution blocked.")
        sys.exit(1)

def main():
    setup_logging()
    logging.info("Starting FaceGate-Linux application wrapper.")

    # Prevent core dumps from leaking encryption keys from memory
    try:
        import ctypes
        PR_SET_DUMPABLE = 4
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(PR_SET_DUMPABLE, 0)
        logging.info("Core dumps disabled (PR_SET_DUMPABLE=0).")
    except Exception as e:
        logging.warning(f"Could not disable core dumps: {e}")

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
    
    args, unknown = parser.parse_known_args()

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
                        "RequestAuth",
                        ["Settings Access"],
                        300000
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
            
            if dbus_active:
                if not dbus_success:
                    logging.info("Settings Access: Verification failed via daemon. Exiting.")
                    sys.exit(1)
            else:
                # Fallback to local AuthDialog
                logging.info("FaceGate daemon is not active on D-Bus. Running local verification.")
                mode = "face" if os.path.exists(EMBEDDING_FILE) else "password"
                timeout_sec = config.get("app_monitor.auth_timeout_seconds", 60)
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
                    logging.info("Requesting Enrollment Access authorization via running FaceGate daemon...")
                    raw_reply = interface.callWithArgumentList(
                        QDBus.CallMode.Block,
                        "RequestAuth",
                        ["Enrollment Access"],
                        300000
                    )
                    reply = QDBusReply(raw_reply)
                    if reply.isValid():
                        dbus_success = reply.value()

            if dbus_active:
                if not dbus_success:
                    print("Error: Enrollment Access verification failed via daemon. Access denied.", file=sys.stderr)
                    sys.exit(1)
            else:
                # Daemon is not active: require master password verification
                if sys.stdin.isatty():
                    try:
                        pwd = getpass.getpass("Enter master password to authorize enrollment: ")
                    except (EOFError, KeyboardInterrupt):
                        print("\nEnrollment cancelled.", file=sys.stderr)
                        sys.exit(1)
                    if not verify_password(pwd):
                        print("Error: Incorrect master password. Enrollment access denied.", file=sys.stderr)
                        sys.exit(1)
                else:
                    print("Error: Master password required to authorize enrollment in non-interactive mode.", file=sys.stderr)
                    sys.exit(1)
        else:
            # First-run setup: no master password set yet
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

        from recognition.cli_enroll import enroll_user
        enroll_user(args.enroll)
        sys.exit(0)
        
    elif args.recognize:
        # Recognition subprocess mode (GUI)
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
        
        # Always launch in face mode if database exists, so camera window pops up first.
        from database.embedding_store import EMBEDDING_FILE, OLD_EMBEDDING_FILE
        mode = "face" if (os.path.exists(EMBEDDING_FILE) or os.path.exists(OLD_EMBEDDING_FILE)) else "password"
        logging.info(f"Recognition subprocess launching in '{mode}' mode (Face Recognition first).")
        
        dialog = AuthDialog(app_name, mode=mode, timeout_seconds=timeout_sec)
        dialog.setWindowState(Qt.WindowState.WindowActive)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        
        # Ensure window stays on top & takes active focus across Linux desktop managers
        QTimer.singleShot(50, lambda: (dialog.setWindowState(Qt.WindowState.WindowActive), dialog.raise_(), dialog.activateWindow()))
        
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
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
        # Daemon monitor mode
        config = get_config()
        startup_delay = int(config.get("behavior.startup_delay_seconds", 0))
        if startup_delay > 0:
            logging.info(f"Daemon: Delaying startup by {startup_delay} seconds...")
            import time
            time.sleep(startup_delay)
            
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
