import os
import signal
import time
import logging
import threading
from PySide6.QtCore import QObject, Signal
import psutil

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

    def _monitor_loop(self):
        while self.running:
            try:
                # Bypassed if FaceGate monitor is inactive
                if not self.main_app.is_active():
                    time.sleep(self.poll_interval)
                    continue

                protected_apps = self.main_app.get_protected_apps()
                # Create maps from exec name and desktop name to config
                exec_to_app = {}
                for app in protected_apps:
                    exec_name = app.get("executable")
                    if exec_name:
                        exec_to_app[exec_name.lower()] = app

                # Scan running processes
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    try:
                        pid = proc.info['pid']
                        
                        # Skip ourselves
                        if pid == os.getpid():
                            continue
                            
                        # If we already processed this pid, skip
                        if pid in self._seen_pids:
                            continue
                            
                        if not proc.is_running():
                            continue

                        name = proc.info['name']
                        exe = proc.info['exe']
                        
                        match_app = None
                        if name and name.lower() in exec_to_app:
                            match_app = exec_to_app[name.lower()]
                        elif exe:
                            exe_base = os.path.basename(exe).lower()
                            if exe_base in exec_to_app:
                                match_app = exec_to_app[exe_base]

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

                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

                # Housekeep seen PIDs
                active_pids = set(psutil.pids())
                self._seen_pids &= active_pids

            except Exception as e:
                logging.error(f"Error in AppMonitor loop: {e}")

            time.sleep(self.poll_interval)
