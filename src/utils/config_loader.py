import os
import yaml
import logging

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

# Global config instance
_config_instance = None

def get_config():
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
