import cv2
import numpy as np
import logging
import threading
import time
from PySide6.QtCore import QObject, Signal
from utils.config_loader import get_config

def is_ir_frame(frame: np.ndarray) -> bool:
    """
    Heuristical check to determine if a frame is near-grayscale (like an IR camera).
    Compares standard deviation / mean differences between color channels.
    """
    if frame is None or len(frame.shape) < 3:
        return True
    b, g, r = cv2.split(frame)
    diff_rg = np.abs(r.astype(int) - g.astype(int))
    diff_gb = np.abs(g.astype(int) - b.astype(int))
    mean_diff = (np.mean(diff_rg) + np.mean(diff_gb)) / 2.0
    return mean_diff < 5.0

def detect_camera_device() -> int:
    """
    Checks for camera devices, running the IR-vs-RGB heuristic to prefer
    RGB-producing devices. Respects manual config overrides if set.
    """
    config = get_config()
    override = config.get("camera.device_index")
    if override is not None:
        logging.info(f"Using camera device index override from config: {override}")
        return int(override)
        
    best_idx = 0
    max_devices = 5
    for idx in range(max_devices):
        # Prefer CAP_V4L2 explicitly on Linux
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap = cv2.VideoCapture(idx) # Fallback to default backend
            
        if cap.isOpened():
            ret, frame = cap.read()
            cap.release()
            if ret and frame is not None:
                if not is_ir_frame(frame):
                    logging.info(f"Auto-detected RGB camera at index {idx}")
                    return idx
                else:
                    logging.info(f"Detected IR/grayscale camera at index {idx}. Continuing search...")
                    best_idx = idx
                    
    logging.info(f"Fallback: using camera at index {best_idx}")
    return best_idx

def diagnose_camera_error(device_index: int) -> str:
    """
    Diagnoses the cause of a camera open failure on Linux.
    """
    import os
    dev_path = f"/dev/video{device_index}"
    if not os.path.exists(dev_path):
        return f"Device not found: '{dev_path}' does not exist."
        
    # Check permissions
    if not os.access(dev_path, os.R_OK):
        import grp
        import getpass
        username = getpass.getuser()
        try:
            video_group = grp.getgrnam("video")
            in_group = username in video_group.gr_mem
        except Exception:
            in_group = False
            
        msg = f"Permission denied: cannot read '{dev_path}'."
        if not in_group:
            msg += f" User '{username}' is not in the 'video' group."
        return msg
        
    return f"Device busy: '{dev_path}' is already in use by another process."

class CameraSignals(QObject):
    frame_ready = Signal(object)  # Emits np.ndarray
    error = Signal(str)

class CameraWorker:
    def __init__(self, device_index: int = None):
        if device_index is None:
            self.device_index = detect_camera_device()
        else:
            self.device_index = device_index
            
        self.signals = CameraSignals()
        self.running = False
        self.thread = None
        self.cap = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logging.info(f"CameraWorker thread started for device index {self.device_index}")

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            try:
                self.thread.join(timeout=1.0)
            except Exception:
                pass
        logging.info("CameraWorker thread stop signaled.")

    def _run(self):
        # Open video capture with V4L2, fallback if needed
        self.cap = cv2.VideoCapture(self.device_index, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.device_index)
            
        if not self.cap.isOpened():
            err_msg = diagnose_camera_error(self.device_index)
            logging.error(err_msg)
            self.signals.error.emit(err_msg)
            return

        # Configure frame dimensions from config
        config = get_config()
        width = config.get("camera.width", 640)
        height = config.get("camera.height", 480)
        fps = config.get("camera.fps", 30)
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        
        # Read frame size back to confirm actual values used
        actual_width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        logging.info(f"Camera opened. Resolution: {actual_width}x{actual_height}")

        target_interval = 1.0 / fps if fps else 0.0
        last_emit = time.monotonic()
        while self.running:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                logging.warning("Failed to grab camera frame")
                time.sleep(0.01)
                continue

            self.signals.frame_ready.emit(frame)

            # Only sleep the *remaining* time to hit the FPS target. Most
            # V4L2 backends already block inside read() until the next frame
            # is available, so unconditionally sleeping a further 1/fps on
            # top (as before) added avoidable per-frame latency. If the
            # driver/backend instead returns frames immediately (e.g. some
            # virtual/loopback devices), this still throttles CPU usage the
            # same as before.
            now = time.monotonic()
            elapsed = now - last_emit
            remaining = target_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            last_emit = time.monotonic()

        self.cap.release()
        self.cap = None
