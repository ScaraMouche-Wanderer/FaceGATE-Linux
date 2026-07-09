import logging
from utils.config_loader import get_config

def verify_password(password: str) -> bool:
    """
    TEMPORARY PLACEHOLDER authentication logic for Phase 1.
    
    WARNING: This logic compares user input against a plaintext password from config.
    This is NOT secure and will be replaced in Phase 3 by secure PBKDF2-tuned 
    password validation and AES-256-GCM credential storage.
    """
    config = get_config()
    configured_password = config.get("auth.placeholder_password", "admin")
    
    success = (password == configured_password)
    
    if success:
        logging.info("Placeholder authentication check: SUCCESS")
    else:
        logging.warning("Placeholder authentication check: FAILURE (Incorrect password)")
        
    return success
