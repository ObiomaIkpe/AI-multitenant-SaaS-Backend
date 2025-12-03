import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(module_name: str, log_dir: str = "logs", level: int = logging.INFO) -> logging.Logger:
    """
    Create and return a logger for the given module.
    Each module gets its own log file named <module_name>.log.
    
    Args:
        module_name (str): Name of the module (used for logger and filename)
        log_dir (str): Directory to store log files
        level (int): Logging level (default INFO)
    
    Returns:
        logging.Logger
    """
    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)
    
    # Logger instance
    logger = logging.getLogger(module_name)
    logger.setLevel(level)
    
    # Prevent adding multiple handlers if the function is called multiple times
    if not logger.handlers:
        # File handler with rotation
        file_path = os.path.join(log_dir, f"{module_name}.log")
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=5
        )
        
        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger
