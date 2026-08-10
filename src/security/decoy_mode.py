"""
Decoy / Honeypot Application Handler for FaceGATE-Linux.

Handles decoy protected applications. When an intruder attempts to launch
a decoy app, FaceGATE silently captures their photo, logs a high-priority
intruder event in the audit trail, and displays a fake application error
dialog or silently terminates the attempt.

Usage:
    from security.decoy_mode import handle_decoy_trigger
    handle_decoy_trigger(app_identifier, frame=latest_frame)
"""

import os
import cv2
import logging
import datetime
from PySide6.QtWidgets import QMessageBox
from database.audit_log import log_auth_attempt


# Generic convincing Linux system error messages for honeypot decoys
FAKE_DECOY_ERRORS = [
    "Segmentation fault (core dumped) in libexec/app-host",
    "Failed to load shared library 'libcrypto.so.1.1': No such file or directory",
    "Application failed to initialize (Error 0x80004005: E_FAIL)",
    "Connection to display server refused: X11 protocol error 12 (BadValue)",
    "Resource temporarily unavailable (errno 11)"
]


def is_decoy_app(app_identifier: str, protected_apps: list) -> bool:
    """Checks if target app identifier is marked as a decoy honeypot."""
    for app in protected_apps:
        if app.get("id") == app_identifier or app.get("desktop_name") == app_identifier:
            return bool(app.get("is_decoy", False))
    return False


def handle_decoy_trigger(app_name: str, frame=None):
    """
    Executes decoy honeypot trap sequence:
    1. Captures intruder selfie frame if available
    2. Logs audit trail with high-priority decoy entry
    3. Displays convincing fake system crash error to confuse snoop
    """
    logging.warning(f"🚨 DECOY APP TRAP TRIGGERED: '{app_name}' was accessed!")

    # 1. Capture intruder selfie
    if frame is not None:
        try:
            intruder_dir = os.path.expanduser("~/.config/facegate/intruders")
            os.makedirs(intruder_dir, exist_ok=True)
            os.chmod(intruder_dir, 0o700)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_app = "".join(c for c in app_name if c.isalnum() or c in ("-", "_")).strip() or "decoy"
            filepath = os.path.join(intruder_dir, f"DECOY_{timestamp}_{safe_app}.jpg")

            cv2.imwrite(filepath, frame)
            os.chmod(filepath, 0o600)
            logging.info(f"Decoy intruder photo captured: {filepath}")
        except Exception as e:
            logging.error(f"Failed to capture decoy photo: {e}")

    # 2. Log in audit trail
    log_auth_attempt(app_name, "decoy_trap", "fail", confidence_score=0.0, username="intruder_trap")

    # 3. Display convincing fake crash message
    import random
    fake_msg = random.choice(FAKE_DECOY_ERRORS)
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setWindowTitle(f"{app_name} Error")
    msg_box.setText(f"Unable to start {app_name}.")
    msg_box.setInformativeText(fake_msg)
    msg_box.exec()
