import subprocess
import ast
import os
import logging

PATH_KEY = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom_facegate/"

def get_current_custom_bindings() -> list:
    try:
        res = subprocess.run(
            ["gsettings", "get", PATH_KEY, "custom-keybindings"],
            capture_output=True, text=True, check=True
        )
        val = res.stdout.strip()
        if not val or val == "@as []" or val == "[]":
            return []
        # Safely parse the list of paths
        return ast.literal_eval(val)
    except Exception as e:
        logging.error(f"Error reading custom-keybindings from gsettings: {e}")
        return []

def register_gnome_hotkey(binding_str: str) -> bool:
    """
    Registers a custom global hotkey in GNOME GSettings.
    Invokes the facegate executable with --emergency-kill flag.
    """
    try:
        bindings = get_current_custom_bindings()
        
        # Add custom path to the list of keybindings if not present
        if CUSTOM_PATH not in bindings:
            bindings.append(CUSTOM_PATH)
            # Re-format list to match what GSettings expects: e.g. ["a", "b"]
            bindings_val = str(bindings).replace("'", '"')
            subprocess.run(
                ["gsettings", "set", PATH_KEY, "custom-keybindings", bindings_val],
                check=True
            )
            
        # Get facegate path
        from locking.launcher_sub import get_facegate_executable
        facegate_exe = get_facegate_executable()
        # Ensure we use an absolute path for local bin if path was generic
        if facegate_exe == "facegate":
            facegate_exe = os.path.expanduser("~/.local/bin/facegate")
            
        cmd_str = f"{facegate_exe} --emergency-kill"
        
        # Write custom properties for this keybinding slot
        sub_schema = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
        custom_full_path = f"{sub_schema}:{CUSTOM_PATH}"
        
        subprocess.run(["gsettings", "set", custom_full_path, "name", "FaceGate Emergency Kill"], check=True)
        subprocess.run(["gsettings", "set", custom_full_path, "command", cmd_str], check=True)
        subprocess.run(["gsettings", "set", custom_full_path, "binding", binding_str], check=True)
        
        logging.info(f"GNOME Emergency Kill hotkey successfully bound to '{binding_str}'.")
        return True
    except Exception as e:
        logging.error(f"Failed to register GNOME emergency hotkey: {e}")
        return False

def unregister_gnome_hotkey() -> bool:
    """
    Removes the custom emergency hotkey from GNOME GSettings.
    """
    try:
        bindings = get_current_custom_bindings()
        if CUSTOM_PATH in bindings:
            bindings.remove(CUSTOM_PATH)
            bindings_val = str(bindings).replace("'", '"')
            subprocess.run(
                ["gsettings", "set", PATH_KEY, "custom-keybindings", bindings_val],
                check=True
            )
            logging.info("GNOME Emergency Kill hotkey successfully unbound.")
        return True
    except Exception as e:
        logging.error(f"Failed to unregister GNOME emergency hotkey: {e}")
        return False

LOCK_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/custom_facegate_lock/"

def register_lock_hotkey(binding_str: str) -> bool:
    """
    Registers the custom global panic lockdown hotkey in GNOME GSettings.
    Invokes the facegate executable with --lock-all flag.
    """
    try:
        bindings = get_current_custom_bindings()
        
        # Add custom path to the list of keybindings if not present
        if LOCK_PATH not in bindings:
            bindings.append(LOCK_PATH)
            bindings_val = str(bindings).replace("'", '"')
            subprocess.run(
                ["gsettings", "set", PATH_KEY, "custom-keybindings", bindings_val],
                check=True
            )
            
        # Get facegate path
        from locking.launcher_sub import get_facegate_executable
        facegate_exe = get_facegate_executable()
        if facegate_exe == "facegate":
            facegate_exe = os.path.expanduser("~/.local/bin/facegate")
            
        cmd_str = f"{facegate_exe} --lock-all"
        
        sub_schema = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
        custom_full_path = f"{sub_schema}:{LOCK_PATH}"
        
        subprocess.run(["gsettings", "set", custom_full_path, "name", "FaceGate Panic Lock"], check=True)
        subprocess.run(["gsettings", "set", custom_full_path, "command", cmd_str], check=True)
        subprocess.run(["gsettings", "set", custom_full_path, "binding", binding_str], check=True)
        
        logging.info(f"GNOME Panic Lockdown hotkey successfully bound to '{binding_str}'.")
        return True
    except Exception as e:
        logging.error(f"Failed to register GNOME panic lockdown hotkey: {e}")
        return False

def unregister_lock_hotkey() -> bool:
    """
    Removes the custom panic lockdown hotkey from GNOME GSettings.
    """
    try:
        bindings = get_current_custom_bindings()
        if LOCK_PATH in bindings:
            bindings.remove(LOCK_PATH)
            bindings_val = str(bindings).replace("'", '"')
            subprocess.run(
                ["gsettings", "set", PATH_KEY, "custom-keybindings", bindings_val],
                check=True
            )
            logging.info("GNOME Panic Lockdown hotkey successfully unbound.")
        return True
    except Exception as e:
        logging.error(f"Failed to unregister GNOME panic lockdown hotkey: {e}")
        return False
