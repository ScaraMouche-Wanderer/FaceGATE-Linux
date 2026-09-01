"""
Presence Sentry (Walk-Away Proximity & Presence Detection) for FaceGATE-Linux.

Periodically inspects user physical presence in front of the screen.
If no authorized face is detected for a configurable idle duration while
sensitive applications are unlocked, automatically re-locks all protected applications.
"""

import time
import logging
import threading
import cv2
import cv2.data
from PySide6.QtCore import QObject, Signal, Slot, QTimer
from utils.config_loader import get_config


class PresenceSentrySignals(QObject):
    presence_lost = Signal()
    presence_restored = Signal()


class PresenceSentry(QObject):
    """
    Lightweight presence monitor that periodically checks whether a user is
    present in front of the screen when protected applications are authorized.
    """

    def __init__(self, check_interval_sec: float = 8.0, timeout_sec: float = 30.0, parent=None):
        super().__init__(parent)
        self.check_interval_sec = check_interval_sec
        self.timeout_sec = timeout_sec
        self.signals = PresenceSentrySignals()
        self.enabled = False
        self.running = False
        
        self.last_presence_time = time.time()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_presence_tick)

        self._detector = None
        self._lock = threading.Lock()

    def start(self):
        """Starts the periodic presence inspection timer."""
        self.running = True
        self.last_presence_time = time.time()
        self._timer.start(int(self.check_interval_sec * 1000))
        logging.info(f"Presence Sentry started (Interval: {self.check_interval_sec}s, Timeout: {self.timeout_sec}s).")

    def stop(self):
        """Stops the presence inspection timer."""
        self.running = False
        self._timer.stop()
        logging.info("Presence Sentry stopped.")

    def record_activity(self):
        """Notifies sentry of active user presence (e.g. recent auth or mouse/key event)."""
        self.last_presence_time = time.time()

    def _check_presence_tick(self):
        if not self.running:
            return

        parent = self.parent()
        if parent and hasattr(parent, "authorized_apps"):
            # If no apps are currently authorized/unlocked, skip presence checking to save CPU/battery
            has_unlocked_apps = any(parent.authorized_apps.values())
            if not has_unlocked_apps:
                self.last_presence_time = time.time()
                return

        # Perform quick camera frame check
        is_present = self._probe_camera_presence()
        now = time.time()

        if is_present:
            self.last_presence_time = now
            self.signals.presence_restored.emit()
        else:
            elapsed = now - self.last_presence_time
            if elapsed >= self.timeout_sec:
                logging.warning(
                    f"Presence Sentry: No user face detected for {elapsed:.1f}s (threshold: {self.timeout_sec}s). "
                    "Triggering automatic walk-away lockdown."
                )
                self.signals.presence_lost.emit()
                self.last_presence_time = now  # Reset to prevent continuous duplicate triggers

    def _probe_camera_presence(self) -> bool:
        """Grabs a single low-res test frame to detect whether any face is present."""
        try:
            import cv2
            from camera.device_enum import find_best_rgb_camera
            cam_idx = find_best_rgb_camera()
            cap = cv2.VideoCapture(cam_idx, cv2.CAP_V4L2)
            if not cap.isOpened():
                cap = cv2.VideoCapture(cam_idx)
            if not cap.isOpened():
                return True  # If camera cannot be opened, fail-safe to assume present

            # Fast grab
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                return True

            # Use OpenCV fast Haar cascade or simple detector if models available
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=3, minSize=(30, 30))

            return len(faces) > 0
        except Exception as e:
            logging.debug(f"Presence probe check error: {e}")
            return True
