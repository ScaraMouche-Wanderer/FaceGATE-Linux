"""
AuthCoordinator controller for FaceGATE-Linux.

Manages process authentication request queue serialization,
backstop recognition subprocess spawning, and admin face verification checks.
"""

import os
import signal
import time
import subprocess
import logging
from PySide6.QtCore import QObject, Slot, QTimer, Qt
from PySide6.QtWidgets import QApplication

def get_process_display_env(pid: int) -> dict:
    """Extracts graphical session display variables from target process /proc/<pid>/environ."""
    env = {}
    target_keys = {
        "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR",
        "QT_QPA_PLATFORM", "XDG_SESSION_TYPE", "DESKTOP_SESSION"
    }
    try:
        environ_path = f"/proc/{pid}/environ"
        if os.path.exists(environ_path):
            with open(environ_path, "rb") as f:
                content = f.read()
            for item in content.split(b"\0"):
                if b"=" in item:
                    k, v = item.split(b"=", 1)
                    k_str = k.decode("utf-8", errors="ignore")
                    if k_str in target_keys:
                        env[k_str] = v.decode("utf-8", errors="ignore")
    except Exception as ex:
        logging.warning(f"Could not extract display environment from /proc/{pid}/environ: {ex}")
    return env


class AuthCoordinator(QObject):
    def __init__(self, config=None, session_manager=None, parent=None):
        super().__init__(parent)
        self.config = config or {}
        self.session_manager = session_manager
        self._auth_queue = []
        self._auth_busy = False

    def verify_admin_face(self, reason: str) -> bool:
        """
        Authenticates using face recognition.
        If there are no enrolled faces (first setup), returns True immediately.
        """
        from security.lockout_manager import is_locked_out
        locked_out, remaining = is_locked_out(reason, is_admin=True)
        if locked_out:
            logging.warning(f"Admin verification for '{reason}' REJECTED due to active lockout ({remaining}s remaining).")
            from database.audit_log import log_auth_attempt
            log_auth_attempt(reason, "lockout", "fail")
            return False

        from database.embedding_store import load_embeddings, EMBEDDING_FILE
        try:
            enrolled = load_embeddings()
        except Exception:
            enrolled = {}

        if not enrolled and not os.path.exists(EMBEDDING_FILE):
            # Distinguish between genuine first-run and tamper attack.
            # If the system was previously initialized (sentinel exists),
            # a missing embedding store means it was deleted — deny access.
            from security.state_watchdog import is_initialized
            if is_initialized():
                deny_mode = self.config.get("security.deny_on_missing_state", True)
                if deny_mode:
                    logging.critical(
                        "TAMPER DETECTED: Encrypted embedding store deleted after "
                        "initialization. Admin verification DENIED. Possible file "
                        "deletion bypass attack."
                    )
                    from database.audit_log import log_auth_attempt
                    log_auth_attempt(reason, "tamper_detected", "fail")
                    return False
                else:
                    logging.warning(
                        "Embedding store missing after initialization but "
                        "deny_on_missing_state is disabled. Allowing access."
                    )

            logging.info("Admin verification: No enrolled faces found and no database exists. Bypassing check.")
            return True

        parent = self.parent()
        if parent and hasattr(parent, "_run_recognition_subprocess"):
            run_sub = parent._run_recognition_subprocess
        else:
            run_sub = self._run_recognition_subprocess

        success, actual_method, score, matched_user = run_sub(reason)

        from database.audit_log import log_auth_attempt
        log_auth_attempt(reason, actual_method, "success" if success else "fail", score, matched_user)
        return success

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

    @Slot(str, int)
    def handle_monitor_auth(self, desktop_name: str, pid: int):
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
            parent = self.parent()
            if parent and hasattr(parent, "_process_auth_request"):
                parent._process_auth_request(desktop_name, pid)
            else:
                self._process_auth_request(desktop_name, pid)
        except Exception as e:
            logging.error(f"Error processing auth request for '{desktop_name}' (PID: {pid}): {e}")
        finally:
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
                
            proc_env = os.environ.copy()
            proc_display_env = get_process_display_env(pid)
            if proc_display_env:
                proc_env.update(proc_display_env)

            logging.info(f"Spawning recognition subprocess for backstop (PID {pid}): {' '.join(cmd)}")
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
            exit_code = proc.returncode
            if exit_code != 0 and stderr_data:
                logging.error(f"Backstop recognition subprocess exit code {exit_code}. Stderr: {stderr_data.strip()}")
            
            logging.info(f"Backstop recognition subprocess exited with code {exit_code}")
            
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

            from database.audit_log import log_auth_attempt
            log_auth_attempt(desktop_name, method, result, confidence, username)
            
            if success:
                from locking.process_controller import resume_process
                resume_process(pid)
                logging.info(f"Resumed process (PID: {pid}) after successful authentication.")
                app_id = self.session_manager.get_app_id_from_desktop(desktop_name)
                self.session_manager.authorize_app(app_id)
            else:
                policy = self.config.get("app_monitor.on_auth_failure", "kill")
                if policy == "kill":
                    from locking.process_controller import terminate_process
                    terminate_process(pid, force=True)
                    logging.info(f"Killed process (PID: {pid}) due to authentication failure.")
                else:
                    logging.info(f"Process (PID: {pid}) remains suspended according to policy '{policy}'.")

                    
        except Exception as e:
            logging.error(f"Error managing process lifecycle: {e}")
