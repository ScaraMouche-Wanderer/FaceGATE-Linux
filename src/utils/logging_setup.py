import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    log_dir = os.path.expanduser("~/.local/share/facegate")
    os.makedirs(log_dir, exist_ok=True)
    os.chmod(log_dir, 0o700)
    log_file = os.path.join(log_dir, "facegate.log")
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Prevent duplicate handlers if initialized multiple times
    if not root_logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s'
        )
        
        # Log to file, rotating at 5 MB, keeping 3 backups
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        
        # Log to console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
    logging.info(f"Logging initialized. Writing to: {log_file}")
