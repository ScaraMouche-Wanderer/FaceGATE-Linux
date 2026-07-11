import os
import shutil
import logging
import sys
from typing import List, Dict

SYSTEM_DESKTOP_DIRS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/applications")
]

USER_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
BACKUP_DIR = os.path.expanduser("~/.config/facegate/backups")

def get_facegate_executable() -> str:
    """
    Resolves the absolute path of the facegate executable.
    Prioritizes shutil.which within the Poetry environment.
    """
    facegate_bin = shutil.which("facegate")
    if facegate_bin:
        return facegate_bin
    
    if sys.argv and sys.argv[0]:
        argv_abs = os.path.abspath(sys.argv[0])
        if os.path.exists(argv_abs) and os.path.basename(argv_abs) == "facegate":
            return argv_abs
            
    return "facegate"

def get_system_desktop_path(desktop_name: str) -> str:
    for directory in SYSTEM_DESKTOP_DIRS:
        # Avoid checking the user directory if we are looking for the original system one
        if directory == USER_DESKTOP_DIR:
            continue
        path = os.path.join(directory, desktop_name)
        if os.path.exists(path):
            return path
    # If not found in system dirs, check user dir (e.g. if it only exists in user dir)
    path = os.path.join(USER_DESKTOP_DIR, desktop_name)
    if os.path.exists(path):
        return path
    return None

_temp_tray = None

def notify_permission_error(desktop_name: str, failing_path: str, error_msg: str):
    """Surfaces a one-time tray notification telling the user protection could not be applied."""
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    app = QApplication.instance()
    if not app:
        return

    found_tray = None
    # Look for an existing QSystemTrayIcon in the application hierarchy
    for obj in app.children():
        if isinstance(obj, QSystemTrayIcon):
            found_tray = obj
            break
        for child in obj.children():
            if isinstance(child, QSystemTrayIcon):
                found_tray = child
                break

    message_title = "FaceGate Protection Failed"
    message_text = f"Could not lock '{desktop_name}' due to a permission error at: {failing_path}. Please check file permissions."

    if found_tray:
        found_tray.showMessage(message_title, message_text, QSystemTrayIcon.MessageIcon.Critical, 10000)
    else:
        global _temp_tray
        _temp_tray = QSystemTrayIcon()
        _temp_tray.show()
        _temp_tray.showMessage(message_title, message_text, QSystemTrayIcon.MessageIcon.Critical, 10000)

def apply_substitution(protected_apps: List[Dict]):
    """
    Substitutes system launchers for protected apps with a FaceGate wrapped command.
    Files are written to user-level ~/.local/share/applications/ to shadow system ones.
    """
    try:
        os.makedirs(USER_DESKTOP_DIR, exist_ok=True)
        os.makedirs(BACKUP_DIR, exist_ok=True)
    except PermissionError as pe:
        failing_path = pe.filename or USER_DESKTOP_DIR
        logging.error(f"PermissionError: Failed to create directories at '{failing_path}': {pe}")
        notify_permission_error("FaceGate System Directories", failing_path, str(pe))
        return
    
    for app in protected_apps:
        desktop_name = app.get("desktop_name")
        if not desktop_name:
            continue
            
        system_path = get_system_desktop_path(desktop_name)
        if not system_path:
            logging.warning(f"Could not find source .desktop file for '{desktop_name}'")
            continue
            
        user_path = os.path.join(USER_DESKTOP_DIR, desktop_name)
        backup_path = os.path.join(BACKUP_DIR, desktop_name)
        
        # Check if the user-level desktop file is already ours
        is_already_substituted = False
        if os.path.exists(user_path):
            try:
                with open(user_path, 'r') as f:
                    content = f.read()
                    if "# Modified by FaceGate" in content:
                        is_already_substituted = True
            except Exception as e:
                logging.error(f"Error reading user desktop file '{desktop_name}': {e}")
                    
        if is_already_substituted:
            logging.info(f"Launcher '{desktop_name}' is already substituted.")
            # Ensure backup exists
            if not os.path.exists(backup_path):
                # Copy from system path to serve as backup
                shutil.copy2(system_path, backup_path)
            continue
            
        # Backup original content
        try:
            if os.path.exists(user_path):
                shutil.copy2(user_path, backup_path)
                logging.info(f"Backed up custom user launcher '{desktop_name}' to {backup_path}")
            else:
                shutil.copy2(system_path, backup_path)
                logging.info(f"Backed up system launcher '{desktop_name}' to {backup_path}")
                
            # Perform modification
            with open(backup_path, 'r') as f:
                lines = f.readlines()
                
            new_lines = ["# Modified by FaceGate\n"]
            in_desktop_entry = False
            exec_modified = False
            
            for line in lines:
                stripped = line.strip()
                if stripped == "[Desktop Entry]":
                    in_desktop_entry = True
                elif stripped.startswith("[") and stripped.endswith("]"):
                    in_desktop_entry = False
                    
                if in_desktop_entry and stripped.startswith("Exec="):
                    orig_exec = stripped[5:]
                    # Rewrite Exec line to run facegate --auth-launch with absolute binary path
                    facegate_bin = get_facegate_executable()
                    new_line = f"Exec={facegate_bin} --auth-launch {desktop_name} -- {orig_exec}\n"
                    new_lines.append(new_line)
                    exec_modified = True
                    logging.info(f"Rewrote Exec for '{desktop_name}': {new_line.strip()}")
                else:
                    new_lines.append(line)
                    
            if not exec_modified:
                logging.warning(f"Could not find Exec line in [Desktop Entry] for '{desktop_name}'")
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                continue
                
            # Write out modified file
            with open(user_path, 'w') as f:
                f.writelines(new_lines)
            logging.info(f"Successfully substituted launcher: {user_path}")
            
        except PermissionError as pe:
            failing_path = pe.filename or user_path
            logging.error(f"Permission denied when modifying launcher '{desktop_name}' at path '{failing_path}': {pe}")
            notify_permission_error(desktop_name, failing_path, str(pe))
        except Exception as e:
            logging.error(f"Failed to substitute launcher '{desktop_name}': {e}")

def restore_substitution(protected_apps: List[Dict]):
    """
    Restores launcher files to their exact pre-substitution state.
    """
    for app in protected_apps:
        desktop_name = app.get("desktop_name")
        if not desktop_name:
            continue
            
        user_path = os.path.join(USER_DESKTOP_DIR, desktop_name)
        backup_path = os.path.join(BACKUP_DIR, desktop_name)
        
        if os.path.exists(user_path):
            was_modified = False
            try:
                with open(user_path, 'r') as f:
                    first_line = f.readline()
                    if "# Modified by FaceGate" in first_line:
                        was_modified = True
            except Exception as e:
                logging.error(f"Error checking user launcher '{desktop_name}' status: {e}")
                
            if was_modified:
                if os.path.exists(backup_path):
                    try:
                        shutil.copy2(backup_path, user_path)
                        logging.info(f"Restored original launcher '{desktop_name}' from backup.")
                    except Exception as e:
                        logging.error(f"Failed to restore launcher '{desktop_name}': {e}")
                else:
                    # If backup doesn't exist, we probably copied from system, so delete the override
                    try:
                        os.remove(user_path)
                        logging.info(f"Removed override launcher '{desktop_name}' (restoring to system default).")
                    except Exception as e:
                        logging.error(f"Failed to remove override launcher '{desktop_name}': {e}")
                        
        # Clean up backup
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except Exception as e:
                logging.warning(f"Failed to remove backup file for '{desktop_name}': {e}")

def check_and_fix_substitutions(protected_apps: List[Dict]):
    """
    Checks if launcher files have been reverted (e.g. by Flatpak/system updates)
    and re-applies substitutions if necessary. Logs whenever a reversion is corrected.
    """
    for app in protected_apps:
        desktop_name = app.get("desktop_name")
        if not desktop_name:
            continue
            
        user_path = os.path.join(USER_DESKTOP_DIR, desktop_name)
        reverted = False
        
        if not os.path.exists(user_path):
            reverted = True
        else:
            try:
                with open(user_path, 'r') as f:
                    content = f.read()
                    if "# Modified by FaceGate" not in content:
                        reverted = True
            except Exception as e:
                logging.error(f"Error checking user launcher '{desktop_name}' for re-check: {e}")
                reverted = True
                
        if reverted:
            logging.warning(f"Launcher Recheck: Reversion detected for '{desktop_name}'. Re-applying substitution.")
            apply_substitution([app])
