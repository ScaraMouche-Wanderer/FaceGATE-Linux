"""
Geofenced Session Awareness for FaceGATE-Linux.

Monitors active Wi-Fi SSID and network subnets. When the system transitions
to an untrusted or unknown network (e.g. laptop moved from home to café),
FaceGATE automatically triggers a Panic Lockdown to re-lock all protected apps.

Usage:
    from security.geofence import GeofenceMonitor, get_current_wifi_ssid
"""

import subprocess
import logging
from PySide6.QtCore import QObject, Signal, QTimer


def get_current_wifi_ssid() -> str | None:
    """Returns the currently connected Wi-Fi SSID, or None if wired/disconnected."""
    try:
        res = subprocess.run(
            ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"],
            capture_output=True, text=True, timeout=2.0
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.startswith("yes:"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass

    # Fallback to iwgetid
    try:
        res = subprocess.run(
            ["iwgetid", "-r"],
            capture_output=True, text=True, timeout=2.0
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    return None


class GeofenceMonitor(QObject):
    """
    Background monitor that periodically checks current Wi-Fi network against trusted list.
    Emits `untrusted_network_detected` when transitioning to an unlisted network.
    """
    untrusted_network_detected = Signal(str)  # Emits current SSID

    def __init__(self, check_interval_sec: int = 15, parent=None):
        super().__init__(parent)
        self.check_interval_ms = check_interval_sec * 1000
        self.last_ssid = get_current_wifi_ssid()
        self.trusted_ssids = []
        self.enabled = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_network)

    def set_trusted_ssids(self, ssids: list, enabled: bool = True):
        self.trusted_ssids = [str(s).strip() for s in ssids if s]
        self.enabled = enabled
        if self.enabled and not self.timer.isActive():
            self.timer.start(self.check_interval_ms)
        elif not self.enabled and self.timer.isActive():
            self.timer.stop()

    def _check_network(self):
        if not self.enabled or not self.trusted_ssids:
            return

        current_ssid = get_current_wifi_ssid()
        if not current_ssid:
            return  # Disconnected or wired ethernet

        if current_ssid != self.last_ssid:
            logging.info(f"Geofence: Network transition detected: '{self.last_ssid}' -> '{current_ssid}'")
            self.last_ssid = current_ssid

            if current_ssid not in self.trusted_ssids:
                logging.warning(f"Geofence: Connected to UNTRUSTED network '{current_ssid}'. Triggering session relock!")
                self.untrusted_network_detected.emit(current_ssid)
