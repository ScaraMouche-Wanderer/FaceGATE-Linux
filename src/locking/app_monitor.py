import os
import time
import logging
import threading
import shutil
from PySide6.QtCore import QObject, Signal
import psutil
import hashlib

# Processes that must NEVER be SIGSTOP'd/SIGKILL'd, even if a SHA-256 match
# fires. This is a last-resort safety net for the "copied binary" heuristic
# below: many unrelated apps (Electron/Chromium/Flatpak/AppImage runtimes in
# particular) legitimately ship a byte-for-byte identical launcher binary,
# so a hash match does NOT reliably mean "this is the same app the user
# protected". Suspending one of these by mistake can freeze/kill core
# session components, which is what produces symptoms like random app
# crashes or the whole desktop session logging out.
CRITICAL_PROCESS_DENYLIST = {
    "gnome-shell", "mutter", "kwin_x11", "kwin_wayland", "plasmashell",
    "xfwm4", "xfce4-session", "sway", "Xorg", "Xwayland", "weston",
    "systemd", "systemd-logind", "dbus-daemon", "dbus-broker",
    "gdm", "gdm3", "sddm", "lightdm", "pulseaudio", "pipewire",
    "pipewire-pulse", "wireplumber", "NetworkManager", "polkitd",
    "gvfsd", "gvfs-daemon", "ibus-daemon", "xdg-desktop-portal",
    "xdg-desktop-portal-gnome", "xdg-desktop-portal-kde", "ssh-agent",
    "gnome-keyring-daemon", "at-spi2-registryd", "facegate",
    "python", "python3", "python3.10", "python3.11", "python3.12",
    "python3.13", "python3.14",
}

def calculate_sha256(filepath):
    """Calculates SHA-256 checksum of the target file to detect copied binaries."""
    try:
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return None

class AppMonitorSignals(QObject):
    # Signal emitted when a protected process is detected and suspended
    # Arguments: (app_desktop_name, pid)
    request_auth = Signal(str, int)

class AppMonitor:
    def __init__(self, main_app, poll_interval=1.5):
        self.main_app = main_app
        self.poll_interval = poll_interval
        self.signals = AppMonitorSignals()
        self.running = False
        self.thread = None
        self._seen_pids = set()  # Tracks (pid, create_time) tuples that have been processed
        self._not_suspicious_pids = set()  # Tracks (pid, create_time) tuples to avoid re-evaluating heuristics
        self._negative_hash_cache = {}  # real_exe -> (mtime, size, last_checked_time)
        
        self._cached_apps = None
        self._canonical_map = {}
        self._hash_map = {}
        self._heuristics = []

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logging.info("AppMonitor background thread started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logging.info("AppMonitor background thread stopped.")

    def clear_seen_pids(self):
        """Clears the seen PIDs history to re-trigger checks for active processes."""
        self._seen_pids.clear()
        self._not_suspicious_pids.clear()

    def _update_cache_if_needed(self, protected_apps):
        """Refreshes canonical paths and SHA-256 hashes if the protected apps list changed."""
        if self._cached_apps == protected_apps:
            return
            
        self._cached_apps = list(protected_apps)
        self._canonical_map = {}
        self._hash_map = {}
        self._heuristics = []
        
        for app in protected_apps:
            exec_name = app.get("executable")
            if not exec_name:
                desktop_name = app.get("desktop_name")
                if desktop_name:
                    from locking.launcher_manager import get_system_desktop_path, extract_primary_executable
                    sys_path = get_system_desktop_path(desktop_name)
                    if sys_path and os.path.exists(sys_path):
                        try:
                            with open(sys_path, 'r', encoding='utf-8', errors='ignore') as f:
                                for line in f:
                                    if line.strip().startswith("Exec="):
                                        exec_name = extract_primary_executable(line.strip()[5:])
                                        break
                        except Exception:
                            pass
            if exec_name:
                path = shutil.which(exec_name)
                if path:
                    real_path = os.path.realpath(path)
                    self._canonical_map[real_path] = app
                    
                    # Cache SHA-256 hash for renamed copy detection
                    h = calculate_sha256(real_path)
                    if h:
                        self._hash_map[h] = app
                        self._heuristics.append((exec_name.lower(), app, h))

    def _monitor_loop(self):
        while self.running:
            try:
                # Bypassed if FaceGate monitor is inactive
                if not self.main_app.is_active():
                    time.sleep(self.poll_interval)
                    continue

                protected_apps = self.main_app.get_protected_apps()
                self._update_cache_if_needed(protected_apps)

                # Scan running processes. 'cmdline' is deliberately NOT requested
                # here - it is one of the more expensive psutil fields to fetch
                # (an extra /proc/<pid>/cmdline read per process) and, before this
                # change, was being fetched eagerly for every single process on
                # every poll tick even though it's only ever inspected for the
                # small subset of processes that reach the gapplication-service
                # check below. It is now fetched lazily, only when needed.
                active_pids = set()
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    try:
                        pid = proc.info['pid']
                        active_pids.add(pid)
                        
                        # Skip ourselves
                        if pid == os.getpid():
                            continue

                        # Use (pid, create_time) as key to handle PID recycling
                        try:
                            proc_key = (pid, proc.create_time())
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                            
                        # If we already processed this (pid, create_time), skip
                        if proc_key in self._seen_pids:
                            continue
                            
                        # If we know this (pid, create_time) is not suspicious, skip
                        if proc_key in self._not_suspicious_pids:
                            continue
                            
                        if not proc.is_running():
                            continue

                        # Skip D-Bus-activated background services (e.g. GNOME gapplication)
                        # NOTE: Only --gapplication-service is skipped. Generic --background
                        # flags are NOT skipped as they can be trivially faked (audit §2.4).
                        try:
                            cmdline = proc.cmdline() or []
                        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                            cmdline = []
                        is_background_service = False
                        for arg in cmdline:
                            if "--gapplication-service" in arg:
                                is_background_service = True
                                break
                                
                        if is_background_service:
                            self._not_suspicious_pids.add(proc_key)
                            continue

                        name = proc.info['name']
                        exe = proc.info['exe']
                        
                        match_app = None
                        if exe:
                            real_exe = os.path.realpath(exe)
                            
                            # 1. Match by canonical absolute path (handles symlinks, dots, alternate PATH layouts)
                            if real_exe in self._canonical_map:
                                match_app = self._canonical_map[real_exe]
                            else:
                                # 2. Match by content SHA-256 hash (detects renamed binaries regardless of process name)
                                if self._hash_map:
                                    cooldown_seconds = 5.0
                                    use_cached_negative = False
                                    try:
                                        stat_res = os.stat(real_exe)
                                        mtime = stat_res.st_mtime
                                        size = stat_res.st_size
                                    except Exception:
                                        mtime = 0.0
                                        size = 0
                                        
                                    if real_exe in self._negative_hash_cache:
                                        cached_mtime, cached_size, cached_time = self._negative_hash_cache[real_exe]
                                        if cached_mtime == mtime and cached_size == size and (time.time() - cached_time < cooldown_seconds):
                                            use_cached_negative = True
                                            
                                    if not use_cached_negative:
                                        proc_hash = calculate_sha256(real_exe)
                                        if proc_hash and proc_hash in self._hash_map:
                                            candidate_app = self._hash_map[proc_hash]
                                            # Defense in depth: a content hash match alone is not
                                            # sufficient proof this is a copy of the SAME app -
                                            # different apps can legitimately ship byte-identical
                                            # launcher binaries (e.g. shared Electron/Chromium
                                            # runtimes). Require the running process name to at
                                            # least share the configured executable's basename
                                            # before trusting the match; otherwise treat it as a
                                            # coincidental collision and skip it.
                                            configured_exec = str(candidate_app.get("executable", "")).lower()
                                            if configured_exec and configured_exec in (name or "").lower():
                                                match_app = candidate_app
                                            else:
                                                logging.warning(
                                                    f"AppMonitor: SHA-256 matched protected app "
                                                    f"'{candidate_app.get('id')}' but process name "
                                                    f"'{name}' doesn't match executable "
                                                    f"'{configured_exec}'. Treating as a hash "
                                                    f"collision and ignoring (likely a shared "
                                                    f"runtime binary, not a real match)."
                                                )
                                                self._negative_hash_cache[real_exe] = (mtime, size, time.time())
                                        else:
                                            self._negative_hash_cache[real_exe] = (mtime, size, time.time())

                        # Safety net: never act on a match involving a critical
                        # session/system process name, regardless of how the
                        # match was made (canonical path or hash fallback).
                        if match_app and name in CRITICAL_PROCESS_DENYLIST:
                            logging.error(
                                f"AppMonitor: SAFETY OVERRIDE - refusing to suspend critical "
                                f"process '{name}' (PID: {pid}) even though it matched "
                                f"protected app '{match_app.get('id')}'. This indicates a "
                                f"false-positive match (likely a SHA-256 collision) and should "
                                f"be reported."
                            )
                            self._not_suspicious_pids.add(proc_key)
                            match_app = None

                        if match_app:
                            app_id = match_app.get("id")
                            desktop_name = match_app.get("desktop_name")

                            # If app is globally authorized, check if session timeout elapsed
                            if self.main_app.is_app_authorized(app_id):
                                timeout = match_app.get("session_timeout_seconds")
                                if timeout is None:
                                    timeout = match_app.get("timeout_seconds")
                                if timeout is None:
                                    timeout = self.main_app.config.get("security.session_timeout_seconds", 300)
                                timeout = int(timeout)

                                canonical_id = self.main_app.get_app_id_from_desktop(app_id)
                                auth_time = self.main_app.auth_timestamps.get(canonical_id, 0)
                                if auth_time and auth_time > 0:
                                    if timeout > 0 and (time.time() - auth_time) > timeout:
                                        logging.info(f"AppMonitor: Session timeout ({timeout}s) elapsed for '{app_id}' (PID: {pid}). Relocking app.")
                                        self.main_app.relock_app(app_id)
                                        self._seen_pids.discard(proc_key)
                                        continue
                                else:
                                    self.main_app.auth_timestamps[canonical_id] = time.time()

                                # Resume process if it was suspended prior to authorization
                                try:
                                    if proc.status() == psutil.STATUS_STOPPED:
                                        logging.info(f"AppMonitor: Resuming authorized suspended process '{name}' (PID: {pid}).")
                                        from locking.process_controller import resume_process
                                        resume_process(pid)
                                except Exception:
                                    pass

                                self._seen_pids.add(proc_key)
                                continue

                            # Check if target app is marked as a Decoy Honeypot
                            if match_app.get("is_decoy", False):
                                logging.warning(f"AppMonitor: Detected Decoy Honeypot process '{name}' (PID: {pid}). Terminating process and triggering trap.")
                                from locking.process_controller import terminate_process
                                terminate_process(pid, force=True)
                                self._seen_pids.add(proc_key)
                                from security.decoy_mode import handle_decoy_trigger
                                handle_decoy_trigger(desktop_name or app_id)
                                continue

                            logging.info(f"AppMonitor: Detected target process '{name}' (PID: {pid}). Suspending.")
                            
                            # Immediately suspend the process via cross-platform controller
                            from locking.process_controller import suspend_process
                            suspend_process(pid)
                            
                            # Mark as seen so we don't suspend it repeatedly

                            self._seen_pids.add(proc_key)
                            
                            # Request authorization (emitted to main GUI thread)
                            self.signals.request_auth.emit(desktop_name, pid)
                        else:
                            # Not a protected app, mark as non-suspicious to skip next iterations
                            self._not_suspicious_pids.add(proc_key)

                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

                # Housekeep seen and non-suspicious (pid, create_time) sets.
                # active_pids was already collected during the scan above, so
                # this avoids a second full process-table walk (psutil.pids())
                # on every tick.
                self._seen_pids = {k for k in self._seen_pids if k[0] in active_pids}
                self._not_suspicious_pids = {k for k in self._not_suspicious_pids if k[0] in active_pids}

            except Exception as e:
                logging.error(f"Error in AppMonitor loop: {e}", exc_info=True)

            time.sleep(self.poll_interval)
