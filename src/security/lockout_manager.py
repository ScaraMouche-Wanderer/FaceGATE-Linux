import os
import json
import time
import logging
import threading

LOCKOUT_FILE = os.path.expanduser("~/.config/facegate/lockout.json")
_lock = threading.Lock()

def _load_lockout_data() -> dict:
    if not os.path.exists(LOCKOUT_FILE):
        # If the system was previously initialized, a missing lockout file
        # means it was deleted — treat as tamper and return max lockout state.
        # This prevents brute-force counter resets via file deletion.
        from security.state_watchdog import is_initialized
        if is_initialized():
            from utils.config_loader import get_config
            try:
                config = get_config()
                deny_mode = config.get("security.deny_on_missing_state", True)
            except Exception:
                deny_mode = True

            if deny_mode:
                logging.critical(
                    "TAMPER DETECTED: Lockout file deleted after initialization. "
                    "Treating as maximum lockout to prevent brute-force counter reset."
                )
                return {
                    "apps": {},
                    "global_attempts": 10,
                    "global_lockout_until": time.time() + 300,  # 5-minute lockout
                }
        return {"apps": {}, "global_attempts": 0, "global_lockout_until": 0.0, "global_last_attempt": 0.0}
    try:
        with open(LOCKOUT_FILE, 'r') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"apps": {}, "global_attempts": 0, "global_lockout_until": 0.0, "global_last_attempt": 0.0}
            data.setdefault("apps", {})
            data.setdefault("global_attempts", 0)
            data.setdefault("global_lockout_until", 0.0)
            data.setdefault("global_last_attempt", 0.0)
            return data
    except Exception as e:
        logging.error(f"Error reading lockout file '{LOCKOUT_FILE}': {e}")
        return {"apps": {}, "global_attempts": 0, "global_lockout_until": 0.0}

def _save_lockout_data(data: dict):
    try:
        os.makedirs(os.path.dirname(LOCKOUT_FILE), exist_ok=True)
        tmp_file = LOCKOUT_FILE + ".tmp"
        fd = os.open(tmp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_file, 0o600)
        os.replace(tmp_file, LOCKOUT_FILE)
    except Exception as e:
        logging.error(f"Error writing lockout file '{LOCKOUT_FILE}': {e}")

def canonicalize_lockout_key(app_name: str, is_admin: bool = False) -> str:
    """
    Canonicalizes a lockout key to prevent attackers from bypassing per-target
    escalating lockout delays using arbitrary or dynamic reason/app strings.
    
    - Admin authentication requests map to the fixed bucket "__admin__".
    - Protected app identifiers are validated against configured protected apps;
      unrecognized identifiers map to the fixed bucket "__unknown_app__".
    """
    if is_admin or not app_name:
        return "__admin__"
        
    if app_name in ("__admin__", "__unknown_app__"):
        return app_name

    # Known admin reason prefixes / actions
    known_admin_prefixes = (
        "Delete ", "Set ", "Re-Enroll ", "Emergency ", "Settings ", "Enrollment ",
        "Export ", "Import ", "Configure ", "Disable ", "Save ", "Access ", "Delete User"
    )
    if any(app_name.startswith(p) for p in known_admin_prefixes):
        return "__admin__"

    try:
        from utils.config_loader import get_config
        config = get_config()
        protected = config.get("protected_apps", [])
        
        key_base = os.path.basename(app_name).removesuffix(".desktop")

        for app in protected:
            if isinstance(app, dict):
                app_id = app.get("id", "")
                desktop_name = app.get("desktop_name", "")
                
                # Check exact matches
                if app_name in (app_id, desktop_name):
                    return app_id or desktop_name
                    
                # Check base name matches
                id_base = os.path.basename(app_id).removesuffix(".desktop") if app_id else ""
                dt_base = os.path.basename(desktop_name).removesuffix(".desktop") if desktop_name else ""
                
                if key_base and (key_base == id_base or key_base == dt_base):
                    return app_id or desktop_name
            elif isinstance(app, str):
                if app_name == app:
                    return app
                app_base = os.path.basename(app).removesuffix(".desktop")
                if key_base == app_base:
                    return app
    except Exception as e:
        logging.error(f"Error in canonicalize_lockout_key: {e}")

    # Unrecognized app identifier -> normalize to standard unknown bucket
    return "__unknown_app__"

def is_locked_out(app_name: str, is_admin: bool = False) -> tuple[bool, int]:
    """
    Checks if app_name or global attempts are currently locked out.
    Returns (is_locked, remaining_seconds).
    """
    app_key = canonicalize_lockout_key(app_name, is_admin=is_admin)
    with _lock:
        data = _load_lockout_data()
        now = time.time()
        
        # Check global lockout
        global_until = data.get("global_lockout_until", 0.0)
        if now < global_until:
            remaining = int(global_until - now) + 1
            return True, remaining

        # Check app-specific lockout
        app_info = data.get("apps", {}).get(app_key, {})
        app_until = app_info.get("lockout_until", 0.0)
        if now < app_until:
            remaining = int(app_until - now) + 1
            return True, remaining

        return False, 0

def record_failed_attempt(app_name: str, is_admin: bool = False) -> tuple[int, float, int]:
    """
    Records a failed authentication attempt for app_name (or admin bucket) and globally.
    Returns (attempts_count, lockout_until_timestamp, remaining_lockout_seconds).
    """
    app_key = canonicalize_lockout_key(app_name, is_admin=is_admin)
    with _lock:
        data = _load_lockout_data()
        now = time.time()

        # Update app-specific attempts
        apps = data.setdefault("apps", {})
        app_info = apps.setdefault(app_key, {"attempts": 0, "lockout_until": 0.0})
        
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

        # Update global attempts (with time-based decay: reset if last attempt was >10 mins ago)
        global_last = data.get("global_last_attempt", 0.0)
        if global_last > 0 and now > global_last + 600:
            data["global_attempts"] = 0
        data["global_attempts"] = data.get("global_attempts", 0) + 1
        data["global_last_attempt"] = now
        if data["global_attempts"] >= 10:
            data["global_lockout_until"] = now + 30

        _save_lockout_data(data)

        remaining = int(delay) if delay > 0 else 0
        return attempts, lockout_until, remaining

def reset_lockout(app_name: str = None, is_admin: bool = False):
    """
    Resets the failed attempt counters and lockout timestamps for app_name (and globally if specified or all).
    """
    with _lock:
        data = _load_lockout_data()
        if app_name:
            app_key = canonicalize_lockout_key(app_name, is_admin=is_admin)
            if app_key in data.get("apps", {}):
                data["apps"][app_key] = {"attempts": 0, "lockout_until": 0.0}
        else:
            data["apps"] = {}

        data["global_attempts"] = 0
        data["global_lockout_until"] = 0.0
        _save_lockout_data(data)

