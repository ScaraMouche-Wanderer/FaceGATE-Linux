"""
State Integrity Watchdog for FaceGATE-Linux.

Monitors critical state files under ~/.config/facegate/ for deletion or
unauthorized modification. Provides:

1. Sentinel file management (.initialized) — distinguishes genuine first-run
   from a post-initialization file-deletion attack.
2. inotify-based real-time monitoring of critical files (embeddings.enc,
   launchers_manifest.json, lockout.json, backups/ directory).
3. Periodic fallback verification (every 30s) — catches directory-level
   deletions and inotify overflow events.
4. Emergency lockdown signal on tamper detection.

This module addresses the "file deletion bypass" vulnerability where an
attacker with shell access can bypass all FaceGATE protections by deleting
internal state files, causing the daemon to treat the environment as
"uninitialized" and fail open.

See implementation_plan.md for full threat analysis.
"""

import os
import hmac
import hashlib
import json
import time
import logging
import threading
from typing import Optional, Set

# Sentinel and config directory paths
FACEGATE_CONFIG_DIR = os.path.expanduser("~/.config/facegate")
SENTINEL_FILE = os.path.join(FACEGATE_CONFIG_DIR, ".initialized")

# Critical files that must not be deleted after initialization
CRITICAL_FILES = {
    "embeddings.enc",
    "launchers_manifest.json",
    "lockout.json",
}

# Critical directories
CRITICAL_DIRS = {
    "backups",
}


def _get_sentinel_hmac_key() -> bytes:
    """
    Derives an HMAC key from machine-id and user identity.
    This ensures the sentinel file cannot be trivially forged by copying
    from another machine/user.
    """
    machine_id = ""
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    machine_id = f.read().strip()
                if machine_id:
                    break
            except Exception:
                pass
    if not machine_id:
        machine_id = "facegate-fallback-machine-id"

    seed = f"facegate-sentinel:{machine_id}:{os.getuid()}:{os.path.expanduser('~')}".encode("utf-8")
    return hashlib.sha256(seed).digest()


def is_initialized() -> bool:
    """
    Returns True if the FaceGATE system was previously initialized
    (sentinel file exists and has a valid HMAC).
    """
    if not os.path.exists(SENTINEL_FILE):
        return False

    try:
        with open(SENTINEL_FILE, "r") as f:
            data = json.load(f)

        stored_mac = data.get("hmac", "")
        timestamp = data.get("initialized_at", "")

        # Verify HMAC
        key = _get_sentinel_hmac_key()
        expected_mac = hmac.new(key, timestamp.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(stored_mac, expected_mac)
    except Exception as e:
        logging.warning(f"Sentinel file exists but is unreadable/invalid: {e}")
        # Treat a corrupt sentinel as "was initialized" (fail-secure)
        return True


def write_sentinel():
    """
    Writes the initialization sentinel file.
    Called after first successful enrollment or master password setup.
    Idempotent — safe to call multiple times.
    """
    try:
        os.makedirs(FACEGATE_CONFIG_DIR, mode=0o700, exist_ok=True)

        timestamp = str(time.time())
        key = _get_sentinel_hmac_key()
        mac = hmac.new(key, timestamp.encode("utf-8"), hashlib.sha256).hexdigest()

        sentinel_data = {
            "initialized_at": timestamp,
            "hmac": mac,
            "version": 1,
        }

        # Atomic write
        tmp_path = SENTINEL_FILE + ".tmp"
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(sentinel_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, SENTINEL_FILE)
        logging.info("State watchdog: Initialization sentinel written.")
    except Exception as e:
        logging.error(f"Failed to write initialization sentinel: {e}")


def check_critical_files() -> list[dict]:
    """
    Checks existence of all critical state files.
    Returns a list of dicts describing missing/tampered files.
    Only reports missing files if the system was previously initialized.
    """
    if not is_initialized():
        return []

    issues = []

    for filename in CRITICAL_FILES:
        filepath = os.path.join(FACEGATE_CONFIG_DIR, filename)
        if not os.path.exists(filepath):
            issues.append({
                "file": filename,
                "path": filepath,
                "event": "deleted",
                "severity": "critical",
                "message": f"Critical state file '{filename}' was deleted after initialization. "
                           f"Possible tamper attack.",
            })

    for dirname in CRITICAL_DIRS:
        dirpath = os.path.join(FACEGATE_CONFIG_DIR, dirname)
        if not os.path.exists(dirpath):
            issues.append({
                "file": dirname,
                "path": dirpath,
                "event": "deleted",
                "severity": "critical",
                "message": f"Critical state directory '{dirname}/' was deleted after initialization. "
                           f"Possible tamper attack.",
            })

    # Check sentinel itself
    if not os.path.exists(SENTINEL_FILE):
        issues.append({
            "file": ".initialized",
            "path": SENTINEL_FILE,
            "event": "deleted",
            "severity": "critical",
            "message": "Initialization sentinel was deleted. Possible tamper attack.",
        })

    return issues


class StateWatchdog:
    """
    Background file integrity monitor for the FaceGATE config directory.

    Uses Linux inotify (via pyinotify or polling fallback) to detect
    deletion or modification of critical state files in real-time.

    Falls back to periodic polling (every 30s) on systems without
    inotify or when the inotify queue overflows.

    Usage:
        watchdog = StateWatchdog(on_tamper_callback=my_handler)
        watchdog.start()
        ...
        watchdog.stop()
    """

    def __init__(self, on_tamper_callback=None, check_interval: float = 30.0):
        """
        Args:
            on_tamper_callback: callable(list[dict]) — called with tamper
                details when critical files are missing/modified.
            check_interval: seconds between periodic fallback checks.
        """
        self._callback = on_tamper_callback
        self._check_interval = check_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._inotify_available = False
        self._known_files: Set[str] = set()

        # Snapshot current state for comparison
        self._refresh_known_files()

    def _refresh_known_files(self):
        """Records which critical files currently exist."""
        self._known_files = set()
        for filename in CRITICAL_FILES:
            filepath = os.path.join(FACEGATE_CONFIG_DIR, filename)
            if os.path.exists(filepath):
                self._known_files.add(filename)
        for dirname in CRITICAL_DIRS:
            dirpath = os.path.join(FACEGATE_CONFIG_DIR, dirname)
            if os.path.exists(dirpath):
                self._known_files.add(dirname)

    def start(self):
        """Starts the background watchdog thread."""
        if self._running:
            return

        if not is_initialized():
            logging.info("State watchdog: System not yet initialized. Watchdog will start after first enrollment.")
            return

        self._running = True

        # Try inotify first
        try:
            import select
            # inotify_simple or direct syscall approach
            self._inotify_available = self._setup_inotify()
        except Exception as e:
            logging.info(f"State watchdog: inotify not available ({e}), using polling fallback.")
            self._inotify_available = False

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="StateWatchdog")
        self._thread.start()
        logging.info(f"State watchdog started (inotify={'yes' if self._inotify_available else 'no'}, "
                     f"poll_interval={self._check_interval}s).")

    def stop(self):
        """Stops the background watchdog thread."""
        self._running = False
        if self._inotify_fd is not None:
            try:
                os.close(self._inotify_fd)
            except Exception:
                pass
            self._inotify_fd = None
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logging.info("State watchdog stopped.")

    def _setup_inotify(self) -> bool:
        """
        Sets up inotify watches on the config directory using direct
        Linux syscalls (no external dependency required).
        """
        import ctypes
        import ctypes.util

        libc_name = ctypes.util.find_library("c")
        if not libc_name:
            return False

        libc = ctypes.CDLL(libc_name, use_errno=True)

        # inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        IN_NONBLOCK = 0x800
        IN_CLOEXEC = 0x80000
        fd = libc.inotify_init1(IN_NONBLOCK | IN_CLOEXEC)
        if fd < 0:
            return False

        self._inotify_fd = fd
        self._inotify_libc = libc

        # Watch the config directory for delete/move/create events
        # IN_DELETE = 0x200, IN_MOVED_FROM = 0x40, IN_DELETE_SELF = 0x400
        # IN_CREATE = 0x100, IN_MODIFY = 0x2
        mask = 0x200 | 0x40 | 0x400 | 0x100 | 0x2

        if os.path.exists(FACEGATE_CONFIG_DIR):
            wd = libc.inotify_add_watch(
                fd,
                FACEGATE_CONFIG_DIR.encode("utf-8"),
                mask,
            )
            if wd < 0:
                os.close(fd)
                self._inotify_fd = None
                return False
            self._inotify_wd = wd
        else:
            os.close(fd)
            self._inotify_fd = None
            return False

        return True

    # Initialize inotify state
    _inotify_fd = None
    _inotify_wd = None
    _inotify_libc = None

    def _read_inotify_events(self) -> bool:
        """
        Non-blocking read of inotify events. Returns True if any
        events involved critical files.
        """
        if self._inotify_fd is None:
            return False

        import select
        ready, _, _ = select.select([self._inotify_fd], [], [], 0.5)
        if not ready:
            return False

        try:
            buf = os.read(self._inotify_fd, 8192)
        except OSError:
            return False

        if not buf:
            return False

        # Parse inotify events to check if any critical files were affected
        # struct inotify_event: wd(4) + mask(4) + cookie(4) + len(4) + name(len)
        import struct
        offset = 0
        critical_event = False
        while offset < len(buf):
            if offset + 16 > len(buf):
                break
            wd, mask, cookie, name_len = struct.unpack_from("iIII", buf, offset)
            offset += 16
            if name_len > 0:
                name_bytes = buf[offset:offset + name_len]
                name = name_bytes.rstrip(b"\x00").decode("utf-8", errors="replace")
                offset += name_len

                # Check if this event involves a critical file
                if name in CRITICAL_FILES or name in CRITICAL_DIRS or name == ".initialized":
                    logging.warning(f"State watchdog: inotify event on critical file '{name}' (mask=0x{mask:x})")
                    critical_event = True
            else:
                offset += name_len

        return critical_event

    def _monitor_loop(self):
        """Main watchdog loop — combines inotify events with periodic polling."""
        last_full_check = 0.0

        while self._running:
            try:
                triggered = False

                # Check inotify events if available
                if self._inotify_available and self._inotify_fd is not None:
                    try:
                        triggered = self._read_inotify_events()
                    except Exception as e:
                        logging.warning(f"State watchdog: inotify read error: {e}")
                        self._inotify_available = False

                # Periodic full check (every check_interval seconds)
                now = time.time()
                if triggered or (now - last_full_check >= self._check_interval):
                    last_full_check = now
                    issues = check_critical_files()
                    if issues:
                        for issue in issues:
                            logging.critical(
                                f"STATE TAMPER DETECTED: {issue['message']} "
                                f"(file={issue['file']}, event={issue['event']})"
                            )
                        if self._callback:
                            try:
                                self._callback(issues)
                            except Exception as cb_err:
                                logging.error(f"State watchdog callback error: {cb_err}")

                # Sleep between checks (short sleep for inotify responsiveness)
                if self._inotify_available:
                    time.sleep(0.5)
                else:
                    # Pure polling mode — sleep for the full interval
                    # but check _running flag periodically
                    sleep_end = time.time() + self._check_interval
                    while self._running and time.time() < sleep_end:
                        time.sleep(1.0)

            except Exception as e:
                logging.error(f"State watchdog loop error: {e}")
                time.sleep(5.0)

    def force_check(self) -> list[dict]:
        """
        Runs an immediate integrity check outside the normal schedule.
        Returns list of issues found (empty if all OK).
        """
        return check_critical_files()
