import os
import signal
import time
import logging
import threading
import shutil
from PySide6.QtCore import QObject, Signal
import psutil
import hashlib

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
        self._seen_pids = set()  # Tracks PIDs that have been processed
        self._not_suspicious_pids = set()  # Tracks non-matching PIDs to avoid re-evaluating heuristics
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

                # Scan running processes
                for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                    try:
                        pid = proc.info['pid']
                        
                        # Skip ourselves
                        if pid == os.getpid():
                            continue
                            
                        # If we already processed this pid, skip
                        if pid in self._seen_pids:
                            continue
                            
                        # If we know this PID is not suspicious, skip
                        if pid in self._not_suspicious_pids:
                            continue
                            
                        if not proc.is_running():
                            continue

                        # Skip background services like --gapplication-service or background daemon mode
                        cmdline = proc.info.get('cmdline') or []
                        is_background_service = False
                        for arg in cmdline:
                            if "--gapplication-service" in arg or "--background" in arg:
                                is_background_service = True
                                break
                                
                        if is_background_service:
                            self._not_suspicious_pids.add(pid)
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
                                # 2. Match by content hash if the process name is suspicious
                                name_lower = name.lower() if name else ""
                                exe_base = os.path.basename(real_exe).lower()
                                
                                is_suspicious = False
                                target_hash = None
                                target_app = None
                                
                                for target_name, app_cfg, h in self._heuristics:
                                    if target_name in name_lower or target_name in exe_base:
                                        is_suspicious = True
                                        target_hash = h
                                        target_app = app_cfg
                                        break
                                
                                if is_suspicious and target_hash and target_app:
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
                                            
                                    if use_cached_negative:
                                        proc_hash = None
                                    else:
                                        proc_hash = calculate_sha256(real_exe)
                                        if proc_hash != target_hash:
                                            self._negative_hash_cache[real_exe] = (mtime, size, time.time())
                                            
                                    if proc_hash == target_hash:
                                        match_app = target_app

                        if match_app:
                            app_id = match_app.get("id")
                            desktop_name = match_app.get("desktop_name")

                            # If app is globally authorized, check if session timeout elapsed
                            if self.main_app.is_app_authorized(app_id):
                                timeout = int(self.main_app.config.get("security.session_timeout_seconds", 300))
                                auth_time = self.main_app.auth_timestamps.get(app_id, 0)
                                if timeout > 0 and (time.time() - auth_time) > timeout:
                                    logging.info(f"AppMonitor: Session timeout elapsed for '{app_id}' (PID: {pid}). Relocking app.")
                                    self.main_app.relock_app(app_id)
                                    if pid in self._seen_pids:
                                        self._seen_pids.remove(pid)
                                else:
                                    self._seen_pids.add(pid)
                                    continue

                            logging.info(f"AppMonitor: Detected target process '{name}' (PID: {pid}). Suspending via SIGSTOP.")
                            
                            # Immediately suspend the process
                            os.kill(pid, signal.SIGSTOP)
                            
                            # Mark as seen so we don't suspend it repeatedly
                            self._seen_pids.add(pid)
                            
                            # Request authorization (emitted to main GUI thread)
                            self.signals.request_auth.emit(desktop_name, pid)
                        else:
                            # Not a protected app, mark PID as non-suspicious to skip next iterations
                            self._not_suspicious_pids.add(pid)

                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

                # Housekeep seen and non-suspicious PIDs
                active_pids = set(psutil.pids())
                self._seen_pids &= active_pids
                self._not_suspicious_pids &= active_pids

            except Exception as e:
                logging.error(f"Error in AppMonitor loop: {e}", exc_info=True)

            time.sleep(self.poll_interval)
