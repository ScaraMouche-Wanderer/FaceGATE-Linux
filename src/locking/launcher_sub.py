import os
import sys
import ctypes
import logging
from typing import List, Dict, Optional

# Preload libc and librt with RTLD_GLOBAL to resolve GLIBC symbol conflicts on Linux
try:
    ctypes.CDLL("libc.so.6", mode=ctypes.RTLD_GLOBAL)
except Exception:
    pass
try:
    ctypes.CDLL("librt.so.1", mode=ctypes.RTLD_GLOBAL)
except Exception:
    pass

from locking.launcher_manager import (
    LauncherManager,
    is_facegate_launcher,
    get_facegate_cmd,
    get_facegate_executable,
    get_system_desktop_path,
    calculate_checksum,
    refresh_desktop_database,
    extract_primary_executable,
    verify_executable_exists,
    notify_permission_error,
    USER_DESKTOP_DIR as LM_USER_DESKTOP_DIR,
    BACKUP_DIR as LM_BACKUP_DIR,
    MANIFEST_FILE as LM_MANIFEST_FILE,
    SYSTEM_DESKTOP_DIRS as LM_SYSTEM_DESKTOP_DIRS,
    FACEGATE_MARKER
)

SYSTEM_DESKTOP_DIRS = LM_SYSTEM_DESKTOP_DIRS
USER_DESKTOP_DIR = LM_USER_DESKTOP_DIR
BACKUP_DIR = LM_BACKUP_DIR
MANIFEST_FILE = LM_MANIFEST_FILE


def get_manager() -> LauncherManager:
    """Helper to return LauncherManager bound to current module parameters."""
    import locking.launcher_sub as current_mod
    return LauncherManager(
        user_desktop_dir=current_mod.USER_DESKTOP_DIR,
        backup_dir=current_mod.BACKUP_DIR,
        manifest_file=current_mod.MANIFEST_FILE,
        system_desktop_dirs=current_mod.SYSTEM_DESKTOP_DIRS
    )


def load_manifest() -> Dict[str, Dict]:
    return get_manager().load_manifest()


def save_manifest(manifest: Dict[str, Dict]):
    get_manager().save_manifest(manifest)


def apply_substitution(protected_apps: List[Dict]):
    """Applies launcher substitution for all protected apps using LauncherManager."""
    manager = get_manager()
    for app in protected_apps:
        manager.protect_application(app)


def restore_substitution(protected_apps: Optional[List[Dict]] = None):
    """Restores launcher substitution using LauncherManager."""
    manager = get_manager()
    if protected_apps is not None:
        for app in protected_apps:
            desktop_name = app.get("desktop_name")
            if desktop_name:
                manager.unprotect_application(desktop_name)
    else:
        manager.restore_all_launchers()


def check_and_fix_substitutions(protected_apps: List[Dict]):
    """Checks if launchers have been reverted and re-applies substitutions using LauncherManager."""
    manager = get_manager()
    for app in protected_apps:
        desktop_name = app.get("desktop_name")
        if not desktop_name:
            continue
        user_path = os.path.join(manager.user_desktop_dir, desktop_name)
        if not is_facegate_launcher(user_path):
            logging.warning(f"Launcher Recheck: Reversion detected for '{desktop_name}'. Re-applying substitution.")
            manager.protect_application(app)


def emergency_restore_launchers() -> int:
    """Emergency utility to restore ALL launchers using LauncherManager."""
    return get_manager().restore_all_launchers()
