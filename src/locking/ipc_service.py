import os
import subprocess
import time
import logging
from PySide6.QtCore import QObject, Slot, Signal, Qt, ClassInfo
from PySide6.QtDBus import QDBusConnection, QDBusAbstractAdaptor, QDBusContext
from PySide6.QtWidgets import QApplication
from locking.launcher_sub import get_facegate_cmd, get_facegate_executable

def run_recognition_helper(identifier: str, cached_key: bytes | None = None, env: dict | None = None) -> tuple[int, str]:
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

    proc_env = os.environ.copy()
    if env:
        allowed_keys = {
            "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR",
            "QT_QPA_PLATFORM", "XDG_SESSION_TYPE", "DESKTOP_SESSION"
        }
        for k, v in env.items():
            if isinstance(k, str) and isinstance(v, str) and k in allowed_keys:
                proc_env[k] = v

    try:
        proc = subprocess.Popen(
            cmd,
            pass_fds=pass_fds,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            close_fds=True,
            env=proc_env
        )
        if cached_key is not None:
            os.close(r)
            try:
                os.write(w, cached_key)
            finally:
                os.close(w)

        stdout_data, stderr_data = proc.communicate()
        if proc.returncode != 0 and stderr_data:
            logging.error(f"Recognition subprocess exit code {proc.returncode}. Stderr: {stderr_data.strip()}")
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


class ThreadSignalDispatcher(QObject):
    auth_success_signal = Signal(str, object)

    def __init__(self, main_app=None, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.auth_success_signal.connect(self._on_auth_success, Qt.ConnectionType.QueuedConnection)

    @Slot(str, object)
    def _on_auth_success(self, app_identifier: str, target_app):
        try:
            logging.info(f"ThreadSignalDispatcher: Main thread processing auth success for '{app_identifier}'")
            if self.main_app:
                self.main_app.authorize_app(app_identifier)
            if target_app:
                from ui.tray import launch_app_command
                launched = launch_app_command(target_app)
                logging.info(f"ThreadSignalDispatcher: Auto-launched target app '{target_app}' (success={launched})")
        except Exception as e:
            logging.error(f"Error handling main-thread auth success dispatch: {e}")


class FaceGateService(QObject):
    def __init__(self, main_app=None):
        super().__init__()
        self.main_app = main_app
        self.signal_dispatcher = ThreadSignalDispatcher(main_app, self)
        # Instantiate the adaptor to map this QObject to the D-Bus interface
        self.adaptor = FaceGateAdaptor(self)

    def can_auto_authorize(self, app_identifier: str) -> bool:
        if self.main_app and not self.main_app.is_active():
            logging.info("FaceGate is inactive/disabled. Auto-authorizing.")
            return True

        if self.main_app:
            protected = self.main_app.get_protected_apps()
            app_id = self.main_app.get_app_id_from_desktop(app_identifier)

            is_protected = False
            for p in protected:
                if isinstance(p, dict):
                    p_id = p.get("id")
                    p_desk = p.get("desktop_name")
                    if app_identifier in (p_id, p_desk) or app_id in (p_id, p_desk):
                        is_protected = True
                        break
                elif isinstance(p, str):
                    if app_identifier == p or app_id == p:
                        is_protected = True
                        break

            if not is_protected:
                logging.info(f"App '{app_identifier}' (ID: '{app_id}') is not in protected apps list. Auto-authorizing.")
                return True

            if self.main_app.is_app_authorized(app_id) or self.main_app.is_app_authorized(app_identifier):
                logging.info(f"App '{app_identifier}' (ID: '{app_id}') is already authorized in session. Auto-authorizing.")
                return True

        return False

    def is_locked_out_or_decoy(self, app_identifier: str) -> bool:
        if self.main_app:
            protected = self.main_app.get_protected_apps()
            from security.decoy_mode import is_decoy_app, handle_decoy_trigger
            if is_decoy_app(app_identifier, protected):
                logging.warning(f"Decoy Honeypot app '{app_identifier}' triggered via D-Bus!")
                handle_decoy_trigger(app_identifier)
                return True

        from security.lockout_manager import is_locked_out
        locked_out, remaining = is_locked_out(app_identifier)
        if locked_out:
            logging.warning(f"RequestAuth for '{app_identifier}' REJECTED due to active brute-force lockout ({remaining}s remaining).")
            from database.audit_log import log_auth_attempt
            log_auth_attempt(app_identifier, "lockout", "fail")
            return True

        return False

    def request_auth_internal(self, app_identifier: str, env: dict | None = None) -> bool:
        logging.info(f"D-Bus request received: RequestAuth for '{app_identifier}'")
        
        if self.can_auto_authorize(app_identifier):
            return True

        if self.is_locked_out_or_decoy(app_identifier):
            return False

        from database.embedding_store import get_cached_key
        cached_key = get_cached_key()

        # Spawn recognition process asynchronously so D-Bus call completes instantly (< 1ms) without blocking
        def _async_recognition():
            try:
                exit_code, stdout_data = run_recognition_helper(app_identifier, cached_key, env=env)
                logging.info(f"Async recognition for '{app_identifier}' completed with exit code {exit_code}")
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

                from database.audit_log import log_auth_attempt
                log_auth_attempt(app_identifier, method, "success" if success else "fail", score, username)

                from security.lockout_manager import record_failed_attempt, reset_lockout
                if success:
                    reset_lockout(app_identifier)
                    target_app = None
                    if self.main_app:
                        for p in self.main_app.get_protected_apps():
                            if isinstance(p, dict):
                                if app_identifier in (p.get("id"), p.get("desktop_name")):
                                    target_app = p
                                    break
                            elif isinstance(p, str) and app_identifier == p:
                                target_app = p
                                break
                    self.signal_dispatcher.auth_success_signal.emit(app_identifier, target_app or app_identifier)
                else:
                    record_failed_attempt(app_identifier)
            except Exception as e:
                logging.error(f"Error in async recognition handler: {e}")

        import threading
        t = threading.Thread(target=_async_recognition, daemon=True)
        t.start()

        return False

    def request_admin_auth_internal(self, reason: str, env: dict | None = None) -> bool:
        logging.info(f"D-Bus request received: RequestAdminAuth for '{reason}'")
        if not self.main_app:
            return False
        return self.main_app.verify_admin_face(reason)

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
        # On Linux, session D-Bus socket (/run/user/{uid}/bus) is mode 0700 owned by process UID.
        # Kernel Unix socket permissions guarantee all session bus peers belong to current UID.
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

    @Slot(str, dict, result=bool)
    def RequestAuthWithEnv(self, app_identifier: str, env: dict) -> bool:
        if not self._verify_caller_uid():
            return False
        return self.service.request_auth_internal(app_identifier, env=env)

    @Slot(str, result=bool)
    def RequestAdminAuth(self, reason: str) -> bool:
        if not self._verify_caller_uid():
            return False
        return self.service.request_admin_auth_internal(reason)

    @Slot(str, dict, result=bool)
    def RequestAdminAuthWithEnv(self, reason: str, env: dict) -> bool:
        if not self._verify_caller_uid():
            return False
        return self.service.request_admin_auth_internal(reason, env=env)

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


class CrossPlatformIPCServer(QObject):
    """
    Zero-dependency, cross-platform IPC server using QLocalServer (Named Pipes on Windows,
    UNIX Domain Sockets on Linux/macOS). Operates in parallel with D-Bus.
    """
    def __init__(self, service: FaceGateService, parent=None):
        super().__init__(parent)
        self.service = service
        from PySide6.QtNetwork import QLocalServer
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_new_connection)

    def start(self) -> bool:
        from utils.platform_paths import get_ipc_socket_address, is_windows
        addr = get_ipc_socket_address()
        
        from PySide6.QtNetwork import QLocalServer
        # Clean up stale socket on Unix
        if not is_windows() and os.path.exists(addr):
            try:
                os.unlink(addr)
            except OSError:
                pass
        
        QLocalServer.removeServer(addr)
        if not self.server.listen(addr):
            logging.warning(f"CrossPlatformIPCServer: Failed to listen on '{addr}': {self.server.errorString()}")
            return False
        logging.info(f"CrossPlatformIPCServer: Listening on '{addr}' for cross-platform requests.")
        return True

    def _on_new_connection(self):
        import json
        client = self.server.nextPendingConnection()
        if not client:
            return

        def _handle_read():
            data = client.readAll().data().decode("utf-8", errors="ignore")
            if not data:
                return
            try:
                msg = json.loads(data)
                action = msg.get("action", "")
                resp = {"status": "ok", "result": None}

                if action == "Ping":
                    resp["result"] = True
                elif action == "RelockAll":
                    self.service.relock_all_internal()
                    resp["result"] = True
                elif action == "RelockApp":
                    app = msg.get("app", "")
                    self.service.relock_app_internal(app)
                    resp["result"] = True
                elif action == "Enable":
                    resp["result"] = self.service.enable_internal()
                elif action == "Disable":
                    minutes = msg.get("minutes", 15)
                    resp["result"] = self.service.disable_internal(minutes)
                elif action == "RequestAuth":
                    app = msg.get("app", "")
                    resp["result"] = self.service.request_auth_internal(app)
                elif action == "EmergencyKill":
                    self.service.emergency_kill_internal()
                    resp["result"] = True
                else:
                    resp = {"status": "error", "error": f"Unknown action: {action}"}

                out_bytes = json.dumps(resp).encode("utf-8")
                client.write(out_bytes)
                client.flush()
            except Exception as e:
                err_resp = json.dumps({"status": "error", "error": str(e)}).encode("utf-8")
                client.write(err_resp)
                client.flush()
            finally:
                client.disconnectFromServer()

        client.readyRead.connect(_handle_read)


def send_cross_platform_ipc_command(action: str, timeout_ms: int = 4000, **kwargs) -> tuple[bool, any]:
    """
    Sends an IPC command to the running daemon across Linux, macOS, and Windows.
    Returns (success: bool, result_payload: any).
    """
    import json
    from PySide6.QtNetwork import QLocalSocket
    from utils.platform_paths import get_ipc_socket_address

    socket = QLocalSocket()
    addr = get_ipc_socket_address()
    socket.connectToServer(addr)
    if not socket.waitForConnected(timeout_ms):
        return False, None

    payload = {"action": action}
    payload.update(kwargs)
    socket.write(json.dumps(payload).encode("utf-8"))
    socket.flush()

    if socket.waitForReadyRead(timeout_ms):
        raw = socket.readAll().data().decode("utf-8", errors="ignore")
        try:
            res = json.loads(raw)
            if res.get("status") == "ok":
                return True, res.get("result")
        except Exception:
            pass
    socket.disconnectFromServer()
    return False, None


def register_dbus_service(service_obj) -> bool:
    """Registers session D-Bus on Linux or fallback environments."""
    try:
        from PySide6.QtDBus import QDBusConnection
        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            logging.warning("Session D-Bus is not connected. Relying on cross-platform IPC socket.")
            return False
            
        if not bus.registerService("org.facegate.FaceGate"):
            logging.warning("Failed to register D-Bus service name: org.facegate.FaceGate.")
            return False
            
        if not bus.registerObject("/org/facegate/FaceGate", service_obj):
            logging.warning("Failed to register object at path: /org/facegate/FaceGate")
            return False
            
        logging.info("D-Bus service 'org.facegate.FaceGate' registered successfully.")
        return True
    except Exception as e:
        logging.warning(f"D-Bus registration skipped: {e}")
        return False

