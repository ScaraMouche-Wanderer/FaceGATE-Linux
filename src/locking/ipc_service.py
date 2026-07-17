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
        from database.embedding_store import get_cached_key, set_cached_key
        from locking.launcher_sub import get_facegate_executable
        from PySide6.QtWidgets import QApplication
        import time
        
        cached_key = get_cached_key()
        facegate_bin = get_facegate_executable()
        
        cmd = [facegate_bin, "--recognize", app_identifier]
        pass_fds = []
        w = None
        
        if cached_key is not None:
            r, w = os.pipe()
            os.set_inheritable(r, True)
            cmd.extend(["--key-fd", str(r)])
            pass_fds.append(r)
            
        logging.info(f"Spawning recognition subprocess: {facegate_bin} --recognize {app_identifier}")
        
        try:
            proc = subprocess.Popen(cmd, pass_fds=pass_fds, stdout=subprocess.PIPE, text=True, close_fds=True)
            if cached_key is not None:
                os.close(r)
                try:
                    os.write(w, cached_key)
                finally:
                    os.close(w)
            
            # Wait for subprocess while keeping event loop alive
            while proc.poll() is None:
                QApplication.processEvents()
                time.sleep(0.05)
                
            stdout_data, _ = proc.communicate()
            exit_code = proc.returncode
            logging.info(f"Recognition subprocess exited with code {exit_code}")
            
            success = (exit_code == 0)
            method = "face"
            username = None
            
            if success:
                # If subprocess returned a key (hex string on stdout), cache it in daemon!
                if stdout_data:
                    for line in stdout_data.splitlines():
                        line = line.strip()
                        if len(line) == 64 and all(c in "0123456789abcdefABCDEF" for c in line):
                            try:
                                key_bytes = bytes.fromhex(line)
                                if len(key_bytes) == 32:
                                    set_cached_key(key_bytes)
                                    logging.info("Successfully cached key returned from recognition subprocess.")
                                    method = "password"
                            except Exception as ex:
                                logging.error(f"Failed to parse key returned from subprocess: {ex}")
            
            # Write to SQLite audit log
            from database.audit_log import log_auth_attempt
            log_auth_attempt(app_identifier, method, "success" if success else "fail", None, username)
            
            if success and self.main_app:
                self.main_app.authorize_app(app_identifier)
                
            return success
        except Exception as e:
            logging.error(f"Failed to spawn recognition subprocess: {e}")
            return False

    def emergency_kill_internal(self):
        """
        Emergency kill requires master password verification to prevent
        unauthenticated session-bus callers from disabling all protections.
        """
        logging.warning("Emergency kill command received via D-Bus. Requiring authentication.")

        if self.main_app:
            success = self.main_app.verify_admin_face("Emergency Shutdown")
            if not success:
                logging.warning("Emergency kill DENIED: verification failed.")
                try:
                    from database.audit_log import log_auth_attempt
                    log_auth_attempt("facegate-daemon", "emergency_hotkey", "fail", None)
                except Exception:
                    pass
                return

            try:
                from database.audit_log import log_auth_attempt
                log_auth_attempt("facegate-daemon", "emergency_hotkey", "bypass", None)
            except Exception as e:
                logging.error(f"Failed to log emergency kill to audit trail: {e}")

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
