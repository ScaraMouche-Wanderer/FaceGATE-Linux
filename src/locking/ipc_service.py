import logging
from PySide6.QtCore import QObject, Slot, ClassInfo
from PySide6.QtDBus import QDBusConnection, QDBusAbstractAdaptor
from ui.auth_dialog import AuthDialog

class FaceGateService(QObject):
    def __init__(self, main_app=None):
        super().__init__()
        self.main_app = main_app
        # Instantiate the adaptor to map this QObject to the D-Bus interface
        self.adaptor = FaceGateAdaptor(self)

    def request_auth_internal(self, app_identifier: str) -> bool:
        logging.info(f"D-Bus request received: RequestAuth for '{app_identifier}'")
        
        # If the monitor is currently disabled, bypass auth
        if self.main_app and not self.main_app.is_active():
            logging.info("FaceGate is inactive/disabled. Auto-authorizing.")
            return True

        import subprocess
        import os
        from database.embedding_store import get_cached_key
        from locking.launcher_sub import get_facegate_executable
        
        cached_key = get_cached_key()
        if not cached_key:
            from database.embedding_store import EMBEDDING_FILE
            mode = "face" if os.path.exists(EMBEDDING_FILE) else "password"
            logging.info(f"Daemon is locked. Spawning {mode} auth dialog directly in daemon.")
            app_name = self.main_app.get_app_name(app_identifier) if self.main_app else app_identifier
            dialog = AuthDialog(app_name, mode=mode)
            res = dialog.exec()
            success = (res == AuthDialog.DialogCode.Accepted)
            
            from database.audit_log import log_auth_attempt
            method_used = "face" if not dialog.fallback_to_password else "password"
            log_auth_attempt(app_identifier, method_used, "success" if success else "fail", getattr(dialog, "final_score", None), getattr(dialog, "matched_user", None) if success else None)
            
            if success and self.main_app:
                self.main_app.authorize_app(app_identifier)
            return success

        # Daemon is unlocked. Run face recognition!
        facegate_bin = get_facegate_executable()
        logging.info(f"Spawning recognition subprocess: {facegate_bin} --recognize {app_identifier}")
        
        cmd = [facegate_bin, "--recognize", app_identifier]
        pass_fds = []
        r, w = os.pipe()
        os.set_inheritable(r, True)
        cmd.extend(["--key-fd", str(r)])
        pass_fds.append(r)
            
        try:
            proc = subprocess.Popen(cmd, pass_fds=pass_fds, stdout=subprocess.PIPE, text=True, close_fds=True)
            os.close(r)
            try:
                os.write(w, cached_key)
            finally:
                os.close(w)

            # Wait for subprocess to finish while keeping event loop alive
            from PySide6.QtWidgets import QApplication
            import time
            while proc.poll() is None:
                QApplication.processEvents()
                time.sleep(0.05)

            stdout_data, _ = proc.communicate()
            exit_code = proc.returncode
            logging.info(f"Recognition subprocess exited with code {exit_code}")
            
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
            elif exit_code in (3, 4, 10, 11, 12):
                # Fallback to password dialog in daemon process
                logging.info(f"Subprocess returned {exit_code}. Displaying password fallback dialog in daemon.")
                app_name = self.main_app.get_app_name(app_identifier) if self.main_app else app_identifier
                dialog = AuthDialog(app_name, mode="password")
                res = dialog.exec()
                success = (res == AuthDialog.DialogCode.Accepted)
                method = "password"
                result = "success" if success else "fail"
                confidence = None
                username = getattr(dialog, "matched_user", None) if success else None
            else:
                result = "fail"

            # Write to SQLite audit log
            from database.audit_log import log_auth_attempt
            log_auth_attempt(app_identifier, method, result, confidence, username)
                
            if success and self.main_app:
                self.main_app.authorize_app(app_identifier)
                
            return success
        except Exception as e:
            logging.error(f"Failed to spawn recognition subprocess: {e}. Falling back to password dialog.")
            app_name = self.main_app.get_app_name(app_identifier) if self.main_app else app_identifier
            dialog = AuthDialog(app_name, mode="password")
            res = dialog.exec()
            success = (res == AuthDialog.DialogCode.Accepted)
            
            # Log fallback outcome
            from database.audit_log import log_auth_attempt
            log_auth_attempt(app_identifier, "password", "success" if success else "fail", None, getattr(dialog, "matched_user", None) if success else None)
            
            if success and self.main_app:
                self.main_app.authorize_app(app_identifier)
            return success

    def emergency_kill_internal(self):
        """
        Emergency kill requires master password verification to prevent
        unauthenticated session-bus callers from disabling all protections.
        """
        logging.warning("Emergency kill command received via D-Bus. Requiring authentication.")

        # Require authentication before honoring the kill
        from ui.auth_dialog import AuthDialog
        from database.embedding_store import EMBEDDING_FILE
        import os
        mode = "face" if os.path.exists(EMBEDDING_FILE) else "password"
        dialog = AuthDialog("Emergency Shutdown", mode=mode)
        res = dialog.exec()
        if res != AuthDialog.DialogCode.Accepted:
            logging.warning("Emergency kill DENIED: verification failed.")
            try:
                from database.audit_log import log_auth_attempt
                log_auth_attempt("facegate-daemon", "emergency_hotkey", "fail", None)
            except Exception:
                pass
            return

        try:
            from database.audit_log import log_auth_attempt
            log_auth_attempt("facegate-daemon", "emergency_hotkey", "bypass", None,
                             getattr(dialog, "matched_user", None))
        except Exception as e:
            logging.error(f"Failed to log emergency kill to audit trail: {e}")

        if self.main_app:
            self.main_app.quit_app(bypass_protection=True)

    def relock_all_internal(self):
        logging.info("RelockAll command received via D-Bus.")
        if self.main_app:
            self.main_app.relock_all()

    def get_enrolled_users_internal(self) -> str:
        from database.embedding_store import load_embeddings
        try:
            enrolled = load_embeddings()
            return ",".join(enrolled.keys())
        except Exception:
            return ""

@ClassInfo({"D-Bus Interface": "org.facegate.FaceGate"})
class FaceGateAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent: FaceGateService):
        super().__init__(parent)
        self.service = parent

    @Slot(str, result=bool)
    def RequestAuth(self, app_identifier: str) -> bool:
        return self.service.request_auth_internal(app_identifier)

    @Slot(result=str)
    def GetEnrolledUsers(self) -> str:
        return self.service.get_enrolled_users_internal()

    @Slot()
    def EmergencyKill(self):
        self.service.emergency_kill_internal()

    @Slot()
    def RelockAll(self):
        self.service.relock_all_internal()

def register_dbus_service(service_obj) -> bool:
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        logging.error("Failed to connect to Session D-Bus.")
        return False
        
    if not bus.registerService("org.facegate.FaceGate"):
        logging.error("Failed to register D-Bus service name: org.facegate.FaceGate. Is FaceGate already running?")
        return False
        
    if not bus.registerObject("/org/facegate/FaceGate", service_obj):
        logging.error("Failed to register object at path: /org/facegate/FaceGate")
        return False
        
    logging.info("D-Bus service 'org.facegate.FaceGate' registered successfully.")
    return True
