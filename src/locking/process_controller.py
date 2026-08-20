import os
import signal
import logging
import psutil
from utils.platform_paths import is_windows, is_macos, is_linux

def suspend_process(pid: int) -> bool:
    """
    Suspends/freezes execution of target process:
    - On Linux/macOS/POSIX: Uses psutil or SIGSTOP signal.
    - On Windows: Uses psutil (NtSuspendProcess internally).
    Returns True if successfully suspended, False otherwise.
    """
    try:
        proc = psutil.Process(pid)
        proc.suspend()
        return True
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False
    except (psutil.AccessDenied, Exception) as e:
        # Fallback to direct POSIX signal if psutil has permission issues
        if not is_windows() and hasattr(signal, "SIGSTOP"):
            try:
                os.kill(pid, signal.SIGSTOP)
                return True
            except OSError as os_err:
                logging.debug(f"Direct SIGSTOP failed for PID {pid}: {os_err}")
        logging.warning(f"ProcessController: Failed to suspend PID {pid}: {e}")
        return False

def resume_process(pid: int) -> bool:
    """
    Resumes/unfreezes execution of target process:
    - On Linux/macOS/POSIX: Uses psutil or SIGCONT signal.
    - On Windows: Uses psutil (NtResumeProcess internally).
    Returns True if successfully resumed, False otherwise.
    """
    try:
        proc = psutil.Process(pid)
        proc.resume()
        return True
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return False
    except (psutil.AccessDenied, Exception) as e:
        if not is_windows() and hasattr(signal, "SIGCONT"):
            try:
                os.kill(pid, signal.SIGCONT)
                return True
            except OSError as os_err:
                logging.debug(f"Direct SIGCONT failed for PID {pid}: {os_err}")
        logging.warning(f"ProcessController: Failed to resume PID {pid}: {e}")
        return False

def terminate_process(pid: int, force: bool = True) -> bool:
    """
    Terminates target process:
    - If force is True: SIGKILL on POSIX or TerminateProcess on Windows.
    - If force is False: SIGTERM on POSIX or TerminateProcess on Windows.
    Returns True if successfully terminated, False otherwise.
    """
    try:
        proc = psutil.Process(pid)
        if force:
            proc.kill()
        else:
            proc.terminate()
        return True
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return True
    except (psutil.AccessDenied, Exception) as e:
        if not is_windows():
            sig = signal.SIGKILL if (force and hasattr(signal, "SIGKILL")) else signal.SIGTERM
            try:
                os.kill(pid, sig)
                return True
            except OSError:
                pass
        logging.warning(f"ProcessController: Failed to terminate PID {pid}: {e}")
        return False

def is_process_running(pid: int) -> bool:
    """Checks whether PID is currently active."""
    return psutil.pid_exists(pid)
