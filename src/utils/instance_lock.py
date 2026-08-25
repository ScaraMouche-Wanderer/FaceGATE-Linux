"""
Single-instance process locking mechanism for FaceGate.
Ensures only one monitor daemon instance runs at any given time across all desktop environments.
"""

import os
import sys
import logging
from typing import Optional
from utils.platform_paths import get_runtime_dir


class SingleInstanceLock:
    """
    Acquires an exclusive, non-blocking file lock in the user's runtime directory.
    If another process already holds the lock, acquisition fails.
    """

    def __init__(self, lock_name: str = "facegate_daemon"):
        self.lock_name = lock_name
        self.lock_file_path = os.path.join(get_runtime_dir(), f"{lock_name}.lock")
        self._fp = None

    def acquire(self) -> bool:
        """
        Attempts to acquire the lock.
        Returns True if successful, False if another instance is already running.
        """
        try:
            os.makedirs(os.path.dirname(self.lock_file_path), exist_ok=True)
            self._fp = open(self.lock_file_path, "a+")

            if sys.platform in ("win32", "cygwin"):
                import msvcrt
                try:
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_NBLCK, 1)
                    return True
                except (IOError, OSError):
                    return False
            else:
                import fcntl
                try:
                    fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # Write PID into lock file for diagnostic purposes
                    self._fp.seek(0)
                    self._fp.truncate()
                    self._fp.write(f"{os.getpid()}\n")
                    self._fp.flush()
                    return True
                except (IOError, OSError):
                    return False
        except Exception as e:
            logging.warning(f"SingleInstanceLock: Could not acquire lock file '{self.lock_file_path}': {e}")
            return False

    def release(self):
        """Releases the lock file."""
        if self._fp is not None:
            try:
                if sys.platform in ("win32", "cygwin"):
                    import msvcrt
                    self._fp.seek(0)
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
                self._fp.close()
            except Exception:
                pass
            finally:
                self._fp = None
                try:
                    if os.path.exists(self.lock_file_path):
                        os.remove(self.lock_file_path)
                except Exception:
                    pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
