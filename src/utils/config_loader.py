import os
import yaml
import logging

DEFAULT_FILENAME = "default" + ".yaml"

class Config:
    def __init__(self):
        self.settings = {}
        self.load()

    def load(self):
        # 1. Load default config relative to source location
        current_dir = os.path.dirname(os.path.abspath(__file__))
        default_config_path = os.path.abspath(
            os.path.join(current_dir, "..", "..", "config", "default.yaml")
        )
        
        if os.path.exists(default_config_path):
            try:
                with open(default_config_path, 'r') as f:
                    self.settings = yaml.safe_load(f) or {}
            except Exception as e:
                logging.error(f"Error reading default config at {default_config_path}: {e}")
        else:
            logging.warning(f"Default config not found at: {default_config_path}")
            
        # 2. Load user overrides from ~/.config/facegate/config.yaml
        user_config_path = os.path.expanduser("~/.config/facegate/config.yaml")
        if os.path.exists(user_config_path):
            try:
                with open(user_config_path, 'r') as f:
                    user_settings = yaml.safe_load(f) or {}
                    self._deep_merge(self.settings, user_settings)
                logging.info(f"Loaded user config overrides from: {user_config_path}")
            except Exception as e:
                logging.error(f"Error reading user config: {e}")
                
        # Synchronize theme values across behavior and ui namespaces
        theme_val = self.get("behavior.theme") or self.get("ui.theme") or "light"
        if "behavior" not in self.settings or not isinstance(self.settings["behavior"], dict):
            self.settings["behavior"] = {}
        if "ui" not in self.settings or not isinstance(self.settings["ui"], dict):
            self.settings["ui"] = {}
        self.settings["behavior"]["theme"] = theme_val
        self.settings["ui"]["theme"] = theme_val

    def _deep_merge(self, base, overrides):
        for k, v in overrides.items():
            if isinstance(v, dict) and k in base and isinstance(base[k], dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v

    def get(self, key, default=None):
        parts = key.split('.')
        val = self.settings
        for part in parts:
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                return default
        return val

    def reload(self):
        """Hot-reloads configuration from disk without creating a new Config instance.
        
        Includes tamper detection: if the previous config had protected_apps
        entries but the reloaded config has none, the previous list is preserved
        and a CRITICAL warning is logged. This prevents the attack where
        deleting config.yaml causes fallback to default.yaml (empty protected_apps).
        """
        # Snapshot current protected_apps before reload
        previous_apps = self.get("protected_apps", [])

        self.settings = {}
        self.load()

        # Tamper detection: protected_apps disappeared
        new_apps = self.get("protected_apps", [])
        if previous_apps and not new_apps:
            from security.state_watchdog import is_initialized
            if is_initialized():
                deny_mode = self.get("security.deny_on_missing_state", True)
                if deny_mode:
                    logging.critical(
                        "TAMPER DETECTED: protected_apps configuration was emptied "
                        "after initialization (was %d apps, now 0). Preserving "
                        "previous protected apps list.",
                        len(previous_apps),
                    )
                    self.set("protected_apps", previous_apps)

        logging.info("Configuration hot-reloaded from disk.")

    def set(self, key, value):
        parts = key.split('.')
        val = self.settings
        for part in parts[:-1]:
            if part not in val or not isinstance(val[part], dict):
                val[part] = {}
            val = val[part]
        val[parts[-1]] = value

        if key in ("behavior.theme", "ui.theme"):
            if "behavior" in self.settings and isinstance(self.settings["behavior"], dict):
                self.settings["behavior"]["theme"] = value
            if "ui" in self.settings and isinstance(self.settings["ui"], dict):
                self.settings["ui"]["theme"] = value

    def _diff_against_defaults(self, current: dict, defaults: dict) -> dict:
        diff = {}
        for k, v in current.items():
            if k not in defaults:
                diff[k] = v
            elif isinstance(v, dict) and isinstance(defaults.get(k), dict):
                sub_diff = self._diff_against_defaults(v, defaults[k])
                if sub_diff:
                    diff[k] = sub_diff
            elif v != defaults.get(k):
                diff[k] = v
        return diff

    def save(self):
        user_config_path = os.path.expanduser("~/.config/facegate/config.yaml")
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            default_config_path = os.path.abspath(
                os.path.join(current_dir, "..", "..", "config", DEFAULT_FILENAME)
            )
            defaults = {}
            if os.path.exists(default_config_path):
                with open(default_config_path, 'r') as f:
                    defaults = yaml.safe_load(f) or {}

            diff_to_save = self._diff_against_defaults(self.settings, defaults)

            os.makedirs(os.path.dirname(user_config_path), exist_ok=True)
            tmp_path = user_config_path + ".tmp"
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as f:
                yaml.safe_dump(diff_to_save, f, default_flow_style=False, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, user_config_path)
            logging.info(f"Configuration diff saved successfully to {user_config_path}")
            return True
        except Exception as e:
            logging.error(f"Error saving config to {user_config_path}: {e}")
            return False

# Global config instance
_config_instance = None

def get_config():
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
