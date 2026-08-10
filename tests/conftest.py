import subprocess
import logging

def pytest_sessionfinish(session, exitstatus):
    """
    Pytest hook executed automatically after all tests complete.
    Ensures facegate.service systemd user service is automatically restarted and active.
    """
    try:
        subprocess.run(["systemctl", "--user", "reset-failed", "facegate.service"], capture_output=True, timeout=3.0)
        subprocess.run(["systemctl", "--user", "restart", "facegate.service"], capture_output=True, timeout=5.0)
    except Exception as e:
        logging.warning(f"Could not automatically restart facegate.service after pytest: {e}")
