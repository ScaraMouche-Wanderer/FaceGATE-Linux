import os
import subprocess
import time
import logging
from PySide6.QtCore import QObject, Slot, ClassInfo
from PySide6.QtDBus import QDBusConnection, QDBusAbstractAdaptor
from PySide6.QtWidgets import QApplication
from locking.launcher_sub import get_facegate_cmd, get_facegate_executable

def run_recognition_helper(identifier: str, cached_key: bytes | None = None) -> tuple[int, str]:
    cmd = list(get_facegate_cmd())
    cmd.extend(["--recognize", identifier])
    pass_fds = []
    w = None

    if cached_key is not None:
        r, w = os.pipe()
        os.set_inheritable(r, True)
        cmd.extend(["--key-fd", str(r)])
        pass_fds.append(r)

    logging.info(f"Spawning recognition subprocess: {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(cmd, pass_fds=pass_fds, stdout=subprocess.PIPE, text=True, close_fds=True)
        if cached_key is not None:
            os.close(r)
            try:
                os.write(w, cached_key)
            finally:
                os.close(w)

        while proc.poll() is None:
            QApplication.processEvents()
            time.sleep(0.05)

        stdout_data, _ = proc.communicate()
        return proc.returncode, stdout_data
    except Exception as e:
        logging.error(f"Failed to spawn recognition subprocess: {e}")
        if cached_key is not None:
            for fd in (r, w):
                try:
                    os.close(fd)
                except OSError:
                    pass
        return 1, ""


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

        # If the app is already authorized in current session, bypass auth
        if self.main_app:
            app_id = self.main_app.get_app_id_from_desktop(app_identifier)
            if self.main_app.is_app_authorized(app_id):
                logging.info(f"App '{app_identifier}' (ID: '{app_id}') is already authorized in session. Auto-authorizing.")
                return True

        # Check for persistent brute-force lockout
        from security.lockout_manager import is_locked_out
        locked_out, remaining = is_locked_out(app_identifier)
        if locked_out:
            logging.warning(f"RequestAuth for '{app_identifier}' REJECTED due to active brute-force lockout ({remaining}s remaining).")
            from database.audit_log import log_auth_attempt
            log_auth_attempt(app_identifier, "lockout", "fail")
            return False

        from database.embedding_store import get_cached_key, set_cached_key
        cached_key = get_cached_key()
        
        exit_code, stdout_data = run_recognition_helper(app_identifier, cached_key)
        logging.info(f"Recognition subprocess exited with code {exit_code}")
        
        success = (exit_code == 0)
        method = "face"
        username = None
        score = None
        
        if stdout_data:
            for line in stdout_data.splitlines():
                line = line.strip()
                if line.startswith("FACEGATE_METHOD:"):
                    method = line.split(":", 1)[1]
                elif line.startswith("FACEGATE_USER:"):
                    username = line.split(":", 1)[1]
                elif line.startswith("FACEGATE_SCORE:"):
                    try:
                        score = float(line.split(":", 1)[1])
                    except ValueError:
                        pass
                elif len(line) == 64 and all(c in "0123456789abcdefABCDEF" for c in line):
                    try:
                        key_bytes = bytes.fromhex(line)
                        if len(key_bytes) == 32:
                            set_cached_key(key_bytes)
                            logging.info("Successfully cached key returned from recognition subprocess.")
                    except Exception as ex:
                        logging.error(f"Failed to parse key returned from subprocess: {ex}")
        
        # Write to SQLite audit log
        from database.audit_log import log_auth_attempt
        log_auth_attempt(app_identifier, method, "success" if success else "fail", score, username)
        
        if success and self.main_app:
            self.main_app.authorize_app(app_identifier)
            
        return success

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

    def enable_internal(self) -> bool:
        logging.info("D-Bus request received: Enable FaceGate")
        if self.main_app:
            self.main_app.resume()
            return True
        return False

    def disable_internal(self, minutes: int = 15) -> bool:
        logging.info(f"D-Bus request received: Disable FaceGate for {minutes} minutes")
        if self.main_app:
            self.main_app.disable_for(minutes)
            return True
        return False

    def get_enrolled_users_internal(self) -> str:
        from database.embedding_store import load_embeddings
        try:
            enrolled = load_embeddings()
            return ",".join(enrolled.keys())
        except Exception:
            return ""

    def remove_enrolled_user_internal(self, username: str) -> bool:
        """Removes an enrolled user from the face database. Requires admin face verification."""
        logging.info(f"D-Bus request received: RemoveEnrolledUser for '{username}'")

        # Security: require admin face verification before allowing user deletion
        if self.main_app:
            if not self.main_app.verify_admin_face(f"Delete User '{username}'"):
                logging.warning(f"RemoveEnrolledUser DENIED for '{username}': verification failed.")
                return False

        from database.embedding_store import delete_embedding
        try:
            delete_embedding(username)
            logging.info(f"Successfully removed enrolled user '{username}' via D-Bus.")
            return True
        except Exception as e:
            logging.error(f"Failed to remove enrolled user '{username}': {e}")
            return False

    def get_admin_user_internal(self) -> str:
        from database.embedding_store import get_admin_user
        try:
            return get_admin_user() or ""
        except Exception:
            return ""

    def set_admin_user_internal(self, username: str) -> bool:
        """Sets the admin user. Requires admin face verification."""
        logging.info(f"D-Bus request received: SetAdminUser for '{username}'")

        # Security: require admin face verification before allowing admin change
        if self.main_app:
            if not self.main_app.verify_admin_face(f"Set Admin to '{username}'"):
                logging.warning(f"SetAdminUser DENIED for '{username}': verification failed.")
                return False

        from database.embedding_store import set_admin_user
        try:
            set_admin_user(username)
            return True
        except Exception:
            return False

    def get_cached_key_hex_internal(self) -> str:
        """Internal-only method for key transfer via --key-fd pipes.
        NOT exposed on the D-Bus interface to prevent session-bus key exfiltration."""
        from database.embedding_store import get_cached_key
        key = get_cached_key()
        return key.hex() if key else ""

    def update_cached_key_internal(self, key_hex: str) -> bool:
        """Internal-only method for key sync.
        NOT exposed on the D-Bus interface to prevent unauthenticated key injection."""
        try:
            key_bytes = bytes.fromhex(key_hex)
            if len(key_bytes) == 32:
                from database.embedding_store import set_cached_key
                set_cached_key(key_bytes)
                logging.info("Internal key cache updated (not via D-Bus).")
                return True
        except Exception as e:
            logging.error(f"Failed to update cached key: {e}")
        return False

    def reload_config_internal(self) -> bool:
        logging.info("D-Bus request received: ReloadConfig")
        if self.main_app and hasattr(self.main_app, 'reload_config'):
            return self.main_app.reload_config()
        return False

@ClassInfo({"D-Bus Interface": "org.facegate.FaceGate"})
class FaceGateAdaptor(QDBusAbstractAdaptor):
    def __init__(self, parent: FaceGateService):
        super().__init__(parent)
        self.service = parent

    def _verify_caller_uid(self) -> bool:
        msg = self.message()
        if msg.isValid():
            caller_service = msg.service()
            if not caller_service:
                return True
            import os
            from PySide6.QtDBus import QDBusConnection
            bus = QDBusConnection.sessionBus()
            if bus.isConnected() and bus.interface():
                try:
                    owner_reply = bus.interface().serviceUid(caller_service)
                    if owner_reply.isValid():
                        caller_uid = owner_reply.value()
                        if caller_uid != os.getuid():
                            logging.warning(f"D-Bus call REJECTED: Caller UID {caller_uid} != process UID {os.getuid()}")
                            return False
                except Exception as e:
                    logging.debug(f"Caller UID check non-blocking fallback: {e}")
        return True

    @Slot(result=bool)
    def ReloadConfig(self) -> bool:
        if not self._verify_caller_uid():
            return False
        return self.service.reload_config_internal()

    @Slot(str, result=bool)
    def RequestAuth(self, app_identifier: str) -> bool:
        if not self._verify_caller_uid():
            return False
        return self.service.request_auth_internal(app_identifier)

    # NOTE: GetCachedKey and UpdateCachedKey have been deliberately REMOVED from
    # the D-Bus interface. Exposing the raw AES-256 key on the session bus allowed
    # any unprivileged process to exfiltrate or inject the encryption key.
    # Key transfer between processes now uses --key-fd pipe passing only.

    @Slot(result=str)
    def GetEnrolledUsers(self) -> str:
        if not self._verify_caller_uid():
            return ""
        return self.service.get_enrolled_users_internal()

    @Slot(result=str)
    def GetAdminUser(self) -> str:
        if not self._verify_caller_uid():
            return ""
        return self.service.get_admin_user_internal()

    @Slot(str, result=bool)
    def SetAdminUser(self, username: str) -> bool:
        if not self._verify_caller_uid():
            return False
        return self.service.set_admin_user_internal(username)

    @Slot()
    def EmergencyKill(self):
        if not self._verify_caller_uid():
            return
        self.service.emergency_kill_internal()

    @Slot()
    def RelockAll(self):
        if not self._verify_caller_uid():
            return
        self.service.relock_all_internal()

    @Slot(result=bool)
    def Enable(self) -> bool:
        if not self._verify_caller_uid():
            return False
        return self.service.enable_internal()

    @Slot(int, result=bool)
    def Disable(self, minutes: int = 15) -> bool:
        if not self._verify_caller_uid():
            return False
        return self.service.disable_internal(minutes)

    @Slot(str, result=bool)
    def RemoveEnrolledUser(self, username: str) -> bool:
        if not self._verify_caller_uid():
            return False
        return self.service.remove_enrolled_user_internal(username)

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
