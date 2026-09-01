import os
import sys
import ctypes
import shutil
import logging
import json
import hashlib
import time
import subprocess
import shlex
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

SYSTEM_DESKTOP_DIRS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/applications")
]

USER_DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
BACKUP_DIR = os.path.expanduser("~/.config/facegate/backups")
MANIFEST_FILE = os.path.expanduser("~/.config/facegate/launchers_manifest.json")

FACEGATE_MARKER = "# Modified by FaceGate"


_temp_tray = None


def notify_permission_error(desktop_name: str, failing_path: str, error_msg: str):
    """Surfaces a one-time tray notification telling the user protection could not be applied."""
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon
    app = QApplication.instance()
    if not app:
        return

    found_tray = None
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


def atomic_write(filepath: str, content: str, mode_bits: int = 0o644) -> bool:
    """
    Performs atomic file replacement using .tmp file, fsync, and os.replace (rename).
    Prevents partially written or corrupted files on disk.
    """
    tmp_path = filepath + ".tmp"
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode_bits)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode_bits)
        os.replace(tmp_path, filepath)
        return True
    except PermissionError:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise
    except Exception as e:
        logging.error(f"Atomic write failed for '{filepath}': {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False


def calculate_checksum(filepath: str) -> Optional[str]:
    """Calculates SHA-256 checksum of a file on disk."""
    if not os.path.exists(filepath):
        return None
    try:
        hasher = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logging.warning(f"Failed to calculate checksum for '{filepath}': {e}")
        return None


def calculate_content_checksum(content: str) -> str:
    """Calculates SHA-256 checksum of string content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def get_facegate_cmd() -> List[str]:
    """
    Resolves execution command array for FaceGate (as a list of command tokens).
    Supports standalone binary ('facegate'), python script execution, or venv binary.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    monitor_main_path = os.path.abspath(os.path.join(current_dir, "..", "core", "monitor_main.py"))
    if os.path.exists(monitor_main_path):
        return [sys.executable, monitor_main_path]

    python_bin_dir = os.path.dirname(sys.executable)
    fg_in_py = os.path.join(python_bin_dir, "facegate")
    if os.path.exists(fg_in_py) and os.access(fg_in_py, os.X_OK):
        return [os.path.abspath(fg_in_py)]

    user_bin = os.path.expanduser("~/.local/bin/facegate")
    if os.path.exists(user_bin) and os.access(user_bin, os.X_OK):
        return [user_bin]

    facegate_bin = shutil.which("facegate")
    if facegate_bin:
        return [os.path.abspath(facegate_bin)]

    if sys.argv and sys.argv[0]:
        argv_abs = os.path.abspath(sys.argv[0])
        if os.path.exists(argv_abs) and os.path.basename(argv_abs) == "facegate":
            return [argv_abs]

    return ["facegate"]


def get_facegate_executable() -> str:
    """Resolves space-quoted string of facegate executable path or python command for Exec lines."""
    cmd = get_facegate_cmd()
    return " ".join(shlex.quote(arg) for arg in cmd)



def get_system_desktop_path(desktop_name: str, system_desktop_dirs: Optional[List[str]] = None) -> Optional[str]:
    """Finds system desktop entry for a given filename."""
    dirs = system_desktop_dirs if system_desktop_dirs is not None else SYSTEM_DESKTOP_DIRS
    user_dir = USER_DESKTOP_DIR
    for directory in dirs:
        if directory == user_dir:
            continue
        path = os.path.join(directory, desktop_name)
        if os.path.exists(path):
            return path
    path = os.path.join(user_dir, desktop_name)
    if os.path.exists(path):
        return path
    return None


def is_facegate_launcher(filepath: str) -> bool:
    """Checks if a .desktop file was wrapped by FaceGate."""
    if not os.path.exists(filepath):
        return False
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(512)
            return FACEGATE_MARKER in content or "--auth-launch" in content
    except Exception:
        return False


def refresh_desktop_database(target_dir: Optional[str] = None):
    """Refreshes desktop database cache via update-desktop-database."""
    update_bin = shutil.which("update-desktop-database")
    dir_to_update = target_dir if target_dir is not None else USER_DESKTOP_DIR
    if update_bin and os.path.exists(dir_to_update):
        try:
            subprocess.run(
                [update_bin, dir_to_update],
                capture_output=True,
                text=True,
                timeout=5
            )
            logging.info(f"Refreshed desktop database cache at {dir_to_update}")
        except Exception as e:
            logging.warning(f"Could not refresh desktop database: {e}")


def extract_primary_executable(exec_cmd: str) -> Optional[str]:
    """Extracts binary executable name/path from Exec line."""
    if not exec_cmd:
        return None
    try:
        tokens = shlex.split(exec_cmd)
        if not tokens:
            return None
        idx = 0
        while idx < len(tokens):
            tok = tokens[idx]
            if tok == "env" or "=" in tok:
                idx += 1
                continue
            return tok
        return tokens[0]
    except Exception:
        parts = exec_cmd.strip().split()
        return parts[0] if parts else None


def verify_executable_exists(exec_cmd: str) -> bool:
    """Verifies executable in Exec command actually exists."""
    binary = extract_primary_executable(exec_cmd)
    if not binary:
        return False
    if os.path.isabs(binary):
        return os.path.exists(binary) and os.access(binary, os.X_OK)
    return shutil.which(binary) is not None


class LauncherManager:
    """
    Central manager responsible for wrapping, backing up, verifying, restoring,
    and tracking desktop launcher files atomically across FaceGate.
    """

    def __init__(self, user_desktop_dir: Optional[str] = None,
                 backup_dir: Optional[str] = None,
                 manifest_file: Optional[str] = None,
                 system_desktop_dirs: Optional[List[str]] = None):
        self._user_desktop_dir = user_desktop_dir
        self._backup_dir = backup_dir
        self._manifest_file = manifest_file
        self._system_desktop_dirs = system_desktop_dirs

    @property
    def user_desktop_dir(self) -> str:
        return self._user_desktop_dir if self._user_desktop_dir is not None else USER_DESKTOP_DIR

    @property
    def backup_dir(self) -> str:
        return self._backup_dir if self._backup_dir is not None else BACKUP_DIR

    @property
    def manifest_file(self) -> str:
        return self._manifest_file if self._manifest_file is not None else MANIFEST_FILE

    @property
    def system_desktop_dirs(self) -> List[str]:
        return self._system_desktop_dirs if self._system_desktop_dirs is not None else SYSTEM_DESKTOP_DIRS

    def load_manifest(self) -> Dict[str, Dict]:
        """Loads launcher tracking manifest index from disk."""
        if not os.path.exists(self.manifest_file):
            return {}
        try:
            with open(self.manifest_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load launcher manifest '{self.manifest_file}': {e}")
            return {}

    def save_manifest(self, manifest: Dict[str, Dict]) -> bool:
        """Saves launcher tracking manifest index atomically to disk."""
        try:
            content = json.dumps(manifest, indent=4)
            return atomic_write(self.manifest_file, content, mode_bits=0o600)
        except Exception as e:
            logging.error(f"Failed to save launcher manifest '{self.manifest_file}': {e}")
            return False

    def verify_launcher(self, filepath: str) -> bool:
        """
        Validates launcher post-writing:
        - Exec line exists
        - Executable exists
        - Launcher parses correctly ([Desktop Entry] header present)
        - Runs desktop-file-validate if available
        """
        if not os.path.exists(filepath):
            logging.error(f"Launcher validation failed: File '{filepath}' does not exist.")
            return False

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if "[Desktop Entry]" not in content:
                logging.error(f"Launcher validation failed: Missing [Desktop Entry] section in '{filepath}'.")
                return False

            exec_line = None
            for line in content.splitlines():
                line_str = line.strip()
                if line_str.startswith("Exec="):
                    exec_line = line_str[5:]
                    break

            if not exec_line:
                logging.error(f"Launcher validation failed: Missing Exec line in '{filepath}'.")
                return False

            # If wrapped by facegate, check target exec extracted from --
            target_exec = exec_line
            if "--auth-launch" in exec_line and " -- " in exec_line:
                target_exec = exec_line.split(" -- ", 1)[1]

            if not verify_executable_exists(target_exec):
                logging.error(f"Launcher validation failed: Target executable '{target_exec}' does not exist for '{filepath}'.")
                return False

            # Run desktop-file-validate if installed
            validator = shutil.which("desktop-file-validate")
            if validator:
                res = subprocess.run([validator, filepath], capture_output=True, text=True, timeout=5)
                if res.returncode != 0:
                    logging.warning(f"desktop-file-validate warning for '{filepath}': {res.stderr.strip() or res.stdout.strip()}")

            return True

        except Exception as e:
            logging.error(f"Launcher verification error for '{filepath}': {e}")
            return False

    def protect_application(self, app_info: Dict) -> bool:
        """
        Protects an application by creating a complete backup and substituting its launcher.
        Stores: original file contents, original Exec, timestamp, checksum in backup and manifest.
        Validates launcher immediately after writing.
        """
        desktop_name = app_info.get("desktop_name")
        if not desktop_name:
            logging.error("protect_application failed: missing 'desktop_name'")
            return False

        system_path = get_system_desktop_path(desktop_name, self.system_desktop_dirs)
        user_path = os.path.join(self.user_desktop_dir, desktop_name)
        backup_path = os.path.join(self.backup_dir, desktop_name)

        try:
            if is_facegate_launcher(user_path):
                logging.info(f"Launcher '{desktop_name}' is already protected by FaceGate.")
                return True

            # Determine source file
            was_custom_user = False
            source_path = None
            if os.path.exists(user_path) and not is_facegate_launcher(user_path):
                source_path = user_path
                was_custom_user = True
            elif system_path and os.path.exists(system_path):
                source_path = system_path
            else:
                logging.error(f"Cannot protect '{desktop_name}': source .desktop file not found.")
                return False

            # Read original file contents
            with open(source_path, 'r', encoding='utf-8', errors='ignore') as f:
                original_contents = f.read()

            original_checksum = calculate_content_checksum(original_contents)
            now_timestamp = time.time()

            # Step 1: Create backup file atomically
            if not atomic_write(backup_path, original_contents, mode_bits=0o644):
                logging.error(f"Failed to write backup for '{desktop_name}' to '{backup_path}'. Aborting protection.")
                return False

            logging.info(f"Backed up launcher '{desktop_name}' to '{backup_path}' (Checksum: {original_checksum[:8]})")

            # Step 2: Build modified launcher
            lines = original_contents.splitlines(keepends=True)
            new_lines = [f"{FACEGATE_MARKER}\n"]
            in_desktop_entry = False
            exec_modified = False
            orig_exec = ""

            for line in lines:
                stripped = line.strip()
                if stripped == "[Desktop Entry]":
                    in_desktop_entry = True
                elif stripped.startswith("[") and stripped.endswith("]"):
                    in_desktop_entry = False

                if in_desktop_entry and stripped.startswith("Exec="):
                    orig_exec = stripped[5:]
                    if not verify_executable_exists(orig_exec):
                        logging.warning(f"Executable for '{desktop_name}' ({orig_exec}) does not exist. Skipping wrapping.")
                        exec_modified = False
                        break

                    facegate_bin = get_facegate_executable()
                    new_line = f"Exec={facegate_bin} --auth-launch {desktop_name} -- {orig_exec}\n"
                    new_lines.append(new_line)
                    exec_modified = True
                else:
                    new_lines.append(line)

            if not exec_modified:
                logging.error(f"Failed to rewrite Exec line for '{desktop_name}'. Cleaning up backup.")
                if os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                return False

            modified_contents = "".join(new_lines)

            # Step 3: Write modified launcher atomically
            if not atomic_write(user_path, modified_contents, mode_bits=0o644):
                logging.error(f"Failed to write modified launcher '{user_path}'. Restoring backup.")
                return False

            # Step 4: Validate written launcher
            if not self.verify_launcher(user_path):
                logging.error(f"Validation failed for modified launcher '{user_path}'. Reverting to original backup.")
                atomic_write(user_path, original_contents, mode_bits=0o644)
                if os.path.exists(backup_path):
                    try:
                        os.remove(backup_path)
                    except Exception:
                        pass
                return False

            # Step 5: Update manifest index
            manifest = self.load_manifest()
            manifest[desktop_name] = {
                "desktop_name": desktop_name,
                "user_path": user_path,
                "backup_path": backup_path,
                "original_exec": orig_exec,
                "modified_exec": new_lines[1].strip() if len(new_lines) > 1 else "",
                "original_checksum": original_checksum,
                "was_custom_user": was_custom_user,
                "protected": True,
                "timestamp": now_timestamp,
                "modified": True
            }
            self.save_manifest(manifest)
            refresh_desktop_database(self.user_desktop_dir)
            logging.info(f"Successfully protected application launcher: '{desktop_name}'")
            return True

        except PermissionError as pe:
            failing_path = getattr(pe, 'filename', None) or user_path
            logging.error(f"Permission denied when modifying launcher '{desktop_name}' at path '{failing_path}': {pe}")
            notify_permission_error(desktop_name, failing_path, str(pe))
            return False
        except Exception as e:
            logging.error(f"Failed to substitute launcher '{desktop_name}': {e}")
            return False

    def unprotect_application(self, desktop_name: str) -> bool:
        """
        Removes the FaceGate wrap from a launcher, restoring it to run the original application directly.
        """
        return self._unprotect_application_internal(desktop_name)

    unprotect_launcher = unprotect_application

    def _unprotect_application_internal(self, desktop_name: str) -> bool:
        """Restores a single application launcher immediately to its original pre-protection state."""
        user_path = os.path.join(self.user_desktop_dir, desktop_name)
        backup_path = os.path.join(self.backup_dir, desktop_name)
        manifest = self.load_manifest()
        info = manifest.get(desktop_name, {})
        was_custom = info.get("was_custom_user", False)

        system_path = get_system_desktop_path(desktop_name, self.system_desktop_dirs)
        is_system_shadow = system_path and os.path.exists(system_path) and (not was_custom)

        restored_successfully = False

        if is_system_shadow:
            if os.path.exists(user_path):
                try:
                    os.remove(user_path)
                    logging.info(f"Removed shadow override launcher '{desktop_name}' (restored to system default).")
                    restored_successfully = True
                except Exception as e:
                    logging.error(f"Failed to remove shadow launcher '{user_path}': {e}")
                    return False
            else:
                restored_successfully = True
        elif os.path.exists(backup_path):
            try:
                with open(backup_path, 'r', encoding='utf-8', errors='ignore') as f:
                    backup_content = f.read()
                if atomic_write(user_path, backup_content, mode_bits=0o644):
                    logging.info(f"Restored custom launcher '{desktop_name}' from backup file.")
                    restored_successfully = True
                else:
                    logging.error(f"Failed to write backup content back to '{user_path}'.")
                    return False
            except Exception as e:
                logging.error(f"Failed to restore launcher '{desktop_name}' from backup: {e}")
                return False
        else:
            if os.path.exists(user_path) and is_facegate_launcher(user_path):
                try:
                    os.remove(user_path)
                    logging.info(f"Removed FaceGate launcher '{user_path}' with no remaining backup.")
                    restored_successfully = True
                except Exception as e:
                    logging.error(f"Failed to remove launcher '{user_path}': {e}")
                    return False
            else:
                restored_successfully = True

        if restored_successfully:
            if os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception:
                    pass
            if desktop_name in manifest:
                manifest[desktop_name]["protected"] = False
                manifest[desktop_name]["modified"] = False
                manifest[desktop_name]["timestamp"] = time.time()
                self.save_manifest(manifest)
            refresh_desktop_database()
            return True

        return False

    def restore_launcher(self, app_id_or_desktop: str) -> bool:
        """Alias for unprotect_application."""
        desktop_name = app_id_or_desktop
        if not desktop_name.endswith(".desktop"):
            desktop_name += ".desktop"
        return self.unprotect_application(desktop_name)

    def restore_all_launchers(self) -> int:
        """
        Restores ALL managed desktop launchers to their original state.
        Flushes backup files and manifest state.
        """
        logging.info("LauncherManager: Restoring all modified launchers...")
        manifest = self.load_manifest()
        targets = set(manifest.keys())

        if os.path.exists(self.backup_dir):
            for f in os.listdir(self.backup_dir):
                if f.endswith(".desktop"):
                    targets.add(f)

        if os.path.exists(self.user_desktop_dir):
            for f in os.listdir(self.user_desktop_dir):
                if f.endswith(".desktop") and is_facegate_launcher(os.path.join(self.user_desktop_dir, f)):
                    targets.add(f)

        restored_count = 0
        for desktop_name in targets:
            if self.unprotect_application(desktop_name):
                restored_count += 1

        # Clear backups
        if os.path.exists(self.backup_dir):
            for f in os.listdir(self.backup_dir):
                try:
                    os.remove(os.path.join(self.backup_dir, f))
                except Exception:
                    pass

        # Reset manifest
        for k in manifest:
            manifest[k]["protected"] = False
            manifest[k]["modified"] = False
            manifest[k]["timestamp"] = time.time()
        self.save_manifest(manifest)
        refresh_desktop_database()

        logging.info(f"LauncherManager: Successfully restored {restored_count} launcher(s).")
        return restored_count

    def startup_recovery(self, protected_apps: List[Dict]) -> int:
        """
        Performs startup consistency check:
        For each managed or user launcher: if wrapped by FaceGate AND app is not protected,
        restores launcher immediately. Makes FaceGate self-healing after crashes.
        """
        logging.info("LauncherManager: Running startup recovery check...")
        protected_desktops = {app.get("desktop_name") for app in protected_apps if app.get("desktop_name")}
        manifest = self.load_manifest()

        targets = set()
        if os.path.exists(self.user_desktop_dir):
            for fname in os.listdir(self.user_desktop_dir):
                if fname.endswith(".desktop") and is_facegate_launcher(os.path.join(self.user_desktop_dir, fname)):
                    targets.add(fname)
        for fname in manifest:
            if manifest[fname].get("protected", False):
                targets.add(fname)

        recovered = 0
        for desktop_name in targets:
            if desktop_name not in protected_desktops:
                user_path = os.path.join(self.user_desktop_dir, desktop_name)
                if is_facegate_launcher(user_path) or desktop_name in manifest:
                    logging.warning(f"Startup Recovery: Launcher '{desktop_name}' is wrapped but app is not in protected list. Restoring original launcher.")
                    if self.unprotect_application(desktop_name):
                        recovered += 1

        if recovered > 0:
            logging.info(f"Startup Recovery: Restored {recovered} orphaned launcher(s).")
        else:
            logging.info("Startup Recovery: All launchers are consistent with configuration.")

        return recovered


_manager_instance: Optional[LauncherManager] = None

def get_launcher_manager() -> LauncherManager:
    """Returns singleton LauncherManager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = LauncherManager()
    return _manager_instance
