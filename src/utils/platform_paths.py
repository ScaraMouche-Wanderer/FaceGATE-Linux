import os
import sys

def is_linux() -> bool:
    return sys.platform.startswith("linux")

def is_macos() -> bool:
    return sys.platform == "darwin"

def is_windows() -> bool:
    return sys.platform in ("win32", "cygwin")

def get_config_dir() -> str:
    """
    Returns the application configuration directory according to OS conventions:
    - Linux: ~/.config/facegate or $XDG_CONFIG_HOME/facegate
    - macOS: ~/Library/Application Support/FaceGate or ~/.config/facegate
    - Windows: %APPDATA%/FaceGate or ~/.config/facegate
    """
    if is_windows():
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = os.path.join(appdata, "FaceGate")
        else:
            path = os.path.expanduser("~/.config/facegate")
    elif is_macos():
        app_support = os.path.expanduser("~/Library/Application Support/FaceGate")
        path = app_support
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            path = os.path.join(xdg_config, "facegate")
        else:
            path = os.path.expanduser("~/.config/facegate")

    os.makedirs(path, mode=0o700, exist_ok=True)
    return path

def get_data_dir() -> str:
    """
    Returns the persistent application data directory (logs, databases, models):
    - Linux: ~/.local/share/facegate or $XDG_DATA_HOME/facegate
    - macOS: ~/Library/Application Support/FaceGate
    - Windows: %LOCALAPPDATA%/FaceGate
    """
    if is_windows():
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            path = os.path.join(local_appdata, "FaceGate")
        else:
            path = os.path.expanduser("~/.local/share/facegate")
    elif is_macos():
        path = os.path.expanduser("~/Library/Application Support/FaceGate")
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        if xdg_data:
            path = os.path.join(xdg_data, "facegate")
        else:
            path = os.path.expanduser("~/.local/share/facegate")

    os.makedirs(path, mode=0o700, exist_ok=True)
    return path

def get_runtime_dir() -> str:
    """
    Returns the fast runtime/socket directory:
    - Linux: /run/user/<uid>/facegate or ~/.local/share/facegate/.runtime
    - macOS: ~/Library/Caches/FaceGate or ~/.config/facegate/.runtime
    - Windows: %TEMP%/FaceGate or ~/.config/facegate/.runtime
    """
    if is_windows():
        temp = os.environ.get("TEMP") or os.environ.get("TMP")
        if temp:
            path = os.path.join(temp, "FaceGate")
        else:
            path = os.path.join(get_config_dir(), ".runtime")
    elif is_macos():
        path = os.path.expanduser("~/Library/Caches/FaceGate")
    else:
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
        if xdg_runtime and os.path.isdir(xdg_runtime):
            path = os.path.join(xdg_runtime, "facegate")
        else:
            path = os.path.join(get_config_dir(), ".runtime")

    os.makedirs(path, mode=0o700, exist_ok=True)
    return path

def get_ipc_socket_address() -> str:
    """
    Returns the cross-platform IPC socket / named pipe address for FaceGate:
    - Windows: FaceGateIPC (Named pipe: \\\\.\\pipe\\FaceGateIPC)
    - Unix/macOS: Path to UNIX domain socket in get_runtime_dir()
    """
    if is_windows():
        return "FaceGateIPC"
    return os.path.join(get_runtime_dir(), "facegate.sock")
