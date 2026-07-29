import os
import json
import time
import logging
import threading

LOCKOUT_FILE = os.path.expanduser("~/.config/facegate/lockout.json")
_lock = threading.Lock()

def _load_lockout_data() -> dict:
    if not os.path.exists(LOCKOUT_FILE):
        return {"apps": {}, "global_attempts": 0, "global_lockout_until": 0.0}
    try:
        with open(LOCKOUT_FILE, 'r') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"apps": {}, "global_attempts": 0, "global_lockout_until": 0.0}
            data.setdefault("apps", {})
            data.setdefault("global_attempts", 0)
            data.setdefault("global_lockout_until", 0.0)
            return data
    except Exception as e:
        logging.error(f"Error reading lockout file '{LOCKOUT_FILE}': {e}")
        return {"apps": {}, "global_attempts": 0, "global_lockout_until": 0.0}

def _save_lockout_data(data: dict):
    try:
        os.makedirs(os.path.dirname(LOCKOUT_FILE), exist_ok=True)
        with open(LOCKOUT_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        os.chmod(LOCKOUT_FILE, 0o600)
    except Exception as e:
        logging.error(f"Error writing lockout file '{LOCKOUT_FILE}': {e}")

def is_locked_out(app_name: str) -> tuple[bool, int]:
    """
    Checks if app_name or global attempts are currently locked out.
    Returns (is_locked, remaining_seconds).
    """
    with _lock:
        data = _load_lockout_data()
        now = time.time()
        
        # Check global lockout
        global_until = data.get("global_lockout_until", 0.0)
        if now < global_until:
            remaining = int(global_until - now) + 1
            return True, remaining

        # Check app-specific lockout
        app_info = data.get("apps", {}).get(app_name, {})
        app_until = app_info.get("lockout_until", 0.0)
        if now < app_until:
            remaining = int(app_until - now) + 1
            return True, remaining

        return False, 0

def record_failed_attempt(app_name: str) -> tuple[int, float, int]:
    """
    Records a failed password authentication attempt for app_name and globally.
    Returns (attempts_count, lockout_until_timestamp, remaining_lockout_seconds).
    """
    with _lock:
        data = _load_lockout_data()
        now = time.time()

        # Update app-specific attempts
        apps = data.setdefault("apps", {})
        app_info = apps.setdefault(app_name, {"attempts": 0, "lockout_until": 0.0})
        
        # If previous lockout elapsed, reset attempt count if long time passed (>10 mins)
        if app_info.get("lockout_until", 0.0) > 0 and now > app_info.get("lockout_until", 0.0) + 600:
            app_info["attempts"] = 0

        app_info["attempts"] += 1
        attempts = app_info["attempts"]

        delay = 0
        if attempts == 3:
            delay = 2
        elif attempts == 4:
            delay = 5
        elif attempts == 5:
            delay = 15
        elif attempts >= 6:
            delay = 30

        lockout_until = now + delay if delay > 0 else 0.0
        app_info["lockout_until"] = lockout_until

        # Update global attempts
        data["global_attempts"] = data.get("global_attempts", 0) + 1
        if data["global_attempts"] >= 10:
            data["global_lockout_until"] = now + 30

        _save_lockout_data(data)

        remaining = int(delay) if delay > 0 else 0
        return attempts, lockout_until, remaining

def reset_lockout(app_name: str = None):
    """
    Resets the failed attempt counters and lockout timestamps for app_name (and globally if specified or all).
    """
    with _lock:
        data = _load_lockout_data()
        if app_name and app_name in data.get("apps", {}):
            data["apps"][app_name] = {"attempts": 0, "lockout_until": 0.0}
        else:
            data["apps"] = {}

        data["global_attempts"] = 0
        data["global_lockout_until"] = 0.0
        _save_lockout_data(data)
