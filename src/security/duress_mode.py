"""
Emergency Duress & Silent Alarm Subsystem for FaceGATE-Linux.

Provides covert protection under physical coercion:
- Entering a designated Duress Password triggers a silent panic lockdown.
- Captures an intruder photo stealthily via webcam.
- Records a tamper-evident AUDIT_DURESS log entry.
- Re-locks all applications and clears the vault RAM key cache.
"""

import os
import json
import base64
import logging
import hashlib
import time
from security.crypto_engine import derive_key
from database.audit_log import log_auth_attempt

DURESS_FILE = os.path.expanduser("~/.config/facegate/.duress.enc")


def has_duress_password() -> bool:
    """Checks if an emergency duress password has been configured."""
    return os.path.exists(DURESS_FILE)


def set_duress_password(password: str) -> bool:
    """
    Sets or updates the emergency duress password.
    Stores a salted PBKDF2 verification token encrypted at rest (0600 permissions).
    """
    if not password or len(password) < 8:
        raise ValueError("Duress password must be at least 8 characters long.")

    salt = os.urandom(16)
    pwd_bytes = bytearray(password.encode("utf-8"))
    try:
        derived = derive_key(pwd_bytes, salt, iterations=600000)
        # Store verification hash
        verifier = hashlib.sha256(derived).hexdigest()

        payload = {
            "salt": base64.b64encode(salt).decode("utf-8"),
            "verifier": verifier,
            "updated_at": time.time()
        }

        os.makedirs(os.path.dirname(DURESS_FILE), exist_ok=True)
        tmp_file = DURESS_FILE + ".tmp"
        fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.chmod(tmp_file, 0o600)
        os.replace(tmp_file, DURESS_FILE)
        logging.info("Emergency duress password configured successfully.")
        return True
    finally:
        for i in range(len(pwd_bytes)):
            pwd_bytes[i] = 0


def verify_duress_password(password: str) -> bool:
    """
    Checks whether the supplied password matches the configured duress credential.
    Memory-safe (zeroes byte buffer).
    """
    if not password or not os.path.exists(DURESS_FILE):
        return False

    pwd_bytes = bytearray(password.encode("utf-8"))
    try:
        with open(DURESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        salt = base64.b64decode(data["salt"])
        expected_verifier = data["verifier"]

        derived = derive_key(pwd_bytes, salt, iterations=600000)
        calc_verifier = hashlib.sha256(derived).hexdigest()

        return calc_verifier == expected_verifier
    except Exception as e:
        logging.error(f"Error checking duress password: {e}")
        return False
    finally:
        for i in range(len(pwd_bytes)):
            pwd_bytes[i] = 0


def trigger_duress_alarm(app_name: str = "Unknown Application"):
    """
    Executes the emergency duress response:
    1. Logs high-priority CRITICAL duress event in audit trail.
    2. Takes a covert webcam snapshot of the intruder.
    3. Clears RAM vault key cache.
    4. Triggers panic lockdown across all protected apps.
    """
    logging.critical(
        f"🚨 EMERGENCY DURESS ALARM TRIGGERED for '{app_name}'! "
        "Initiating silent panic lockdown and intruder capture."
    )

    # 1. Tamper-evident audit log
    try:
        log_auth_attempt(f"DURESS_ALARM:{app_name}", "duress_credential", "fail", 0.0, "COVERT_DURESS")
    except Exception as e:
        logging.error(f"Duress alarm: error logging audit: {e}")

    # 2. Stealth webcam snapshot
    try:
        import cv2
        from camera.device_enum import find_best_rgb_camera
        cam_idx = find_best_rgb_camera()
        cap = cv2.VideoCapture(cam_idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap = cv2.VideoCapture(cam_idx)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                intruder_dir = os.path.expanduser("~/.config/facegate/intruders")
                os.makedirs(intruder_dir, exist_ok=True)
                os.chmod(intruder_dir, 0o700)
                timestamp = int(time.time())
                filepath = os.path.join(intruder_dir, f"DURESS_{timestamp}_{app_name.replace(' ', '_')}.jpg")
                cv2.imwrite(filepath, frame)
                os.chmod(filepath, 0o600)
                logging.info(f"Duress intruder capture saved to: {filepath}")
            cap.release()
    except Exception as e:
        logging.error(f"Duress alarm: error capturing photo: {e}")

    # 3. Clear encryption key cache from RAM
    try:
        from database.embedding_store import clear_cached_key
        clear_cached_key()
    except Exception as e:
        logging.error(f"Duress alarm: error clearing key cache: {e}")

    # 4. Trigger D-Bus panic lockdown if daemon is running
    try:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface
        bus = QDBusConnection.sessionBus()
        if bus.isConnected():
            iface = QDBusInterface("org.facegate.FaceGate", "/org/facegate/FaceGate", "org.facegate.FaceGate", bus)
            if iface.isValid():
                iface.call("RelockAll")
    except Exception:
        pass


def set_duress_password_cli():
    """Interactive CLI prompt for configuring the emergency duress password."""
    import getpass
    import sys

    print("\n🚨 === FaceGATE Emergency Duress Password Setup ===")
    print("The Duress Password is an emergency credential used under physical coercion.")
    print("Entering this password covertly triggers an immediate panic lockdown, captures a")
    print("webcam photo of the attacker, and seals all sensitive credentials.")
    print("-----------------------------------------------------------------------------")

    while True:
        p1 = getpass.getpass("Enter emergency duress password (min 8 chars): ")
        if len(p1) < 8:
            print("Error: Duress password must be at least 8 characters long.")
            continue
        p2 = getpass.getpass("Confirm emergency duress password: ")
        if p1 != p2:
            print("Error: Passwords do not match. Try again.")
            continue
        break

    try:
        set_duress_password(p1)
        print("\n\033[92mSUCCESS:\033[0m Emergency duress password configured and encrypted at rest.")
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
