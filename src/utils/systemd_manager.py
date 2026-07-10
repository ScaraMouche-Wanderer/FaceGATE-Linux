import subprocess
import logging

def is_enabled() -> bool:
    """
    Checks if facegate.service is enabled in systemd's user manager.
    """
    try:
        res = subprocess.run(
            ["systemctl", "--user", "is-enabled", "facegate.service"],
            capture_output=True,
            text=True
        )
        return res.stdout.strip() == "enabled"
    except Exception as e:
        logging.error(f"Error checking systemd service enabled state: {e}")
        return False

def enable() -> bool:
    """
    Enables facegate.service in systemd's user manager.
    """
    try:
        res = subprocess.run(
            ["systemctl", "--user", "enable", "facegate.service"],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            logging.info("Systemd service 'facegate.service' enabled successfully.")
            return True
        else:
            logging.error(f"Failed to enable systemd service: {res.stderr.strip()}")
            return False
    except Exception as e:
        logging.error(f"Error enabling systemd service: {e}")
        return False

def disable() -> bool:
    """
    Disables facegate.service in systemd's user manager.
    """
    try:
        res = subprocess.run(
            ["systemctl", "--user", "disable", "facegate.service"],
            capture_output=True,
            text=True
        )
        if res.returncode == 0:
            logging.info("Systemd service 'facegate.service' disabled successfully.")
            return True
        else:
            logging.error(f"Failed to disable systemd service: {res.stderr.strip()}")
            return False
    except Exception as e:
        logging.error(f"Error disabling systemd service: {e}")
        return False
