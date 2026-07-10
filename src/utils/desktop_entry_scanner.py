import os
import shlex
import configparser
import logging

def get_installed_desktop_entries() -> list:
    """
    Scans system and user applications directories for installed `.desktop` files.
    Parses application Name, Exec (stripping field codes), and Icon fields.
    Filters out hidden or non-displayable entries.
    Returns a sorted list of dictionaries:
    [{"desktop_name", "name", "executable", "icon", "path"}, ...]
    """
    directories = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications")
    ]
    
    apps = []
    seen_filenames = set()
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    
    for directory in directories:
        if not os.path.exists(directory):
            continue
            
        for filename in os.listdir(directory):
            if not filename.endswith('.desktop'):
                continue
                
            if filename in seen_filenames:
                continue
                
            filepath = os.path.join(directory, filename)
            try:
                parser.clear()
                parser.read(filepath, encoding='utf-8')
                
                if 'Desktop Entry' not in parser:
                    continue
                    
                entry = parser['Desktop Entry']
                
                # Filter out entries marked as Hidden or NoDisplay
                no_display = entry.get('NoDisplay', 'false').lower() == 'true'
                hidden = entry.get('Hidden', 'false').lower() == 'true'
                if no_display or hidden:
                    continue
                    
                name = entry.get('Name')
                exec_str = entry.get('Exec')
                icon = entry.get('Icon', '')
                
                if not name or not exec_str:
                    continue
                    
                # Parse the executable binary name, removing arguments and field codes
                try:
                    tokens = shlex.split(exec_str)
                except Exception:
                    tokens = exec_str.split()
                    
                if not tokens:
                    continue
                    
                # Executable binary is the first token. Get its basename.
                executable_path = tokens[0]
                executable_name = os.path.basename(executable_path)
                
                # Exclude facegate wrappers to prevent self-locking loops
                if executable_name == "facegate":
                    continue
                
                apps.append({
                    "desktop_name": filename,
                    "name": name,
                    "executable": executable_name,
                    "icon": icon,
                    "path": filepath
                })
                seen_filenames.add(filename)
            except Exception as e:
                logging.debug(f"Error parsing desktop file {filename}: {e}")
                
    # Sort alphabetically by Name
    apps.sort(key=lambda x: x["name"].lower())
    return apps
