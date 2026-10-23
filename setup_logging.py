"""
Logging setup for กดจนหลอนTone

Configures logging for the application with console and file handlers.
"""

import logging
import sys
import threading
from pathlib import Path
from datetime import datetime

import config

_LOGGING_INITIALIZED = False
_LOGGING_LOCK = threading.Lock()


def setup_logging(log_level: str = None, log_to_file: bool = True, force: bool = False):
    """
    Setup logging configuration for the application (idempotent).
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to file in addition to console
        force: Force re-initialization even if already configured
    """
    global _LOGGING_INITIALIZED

    with _LOGGING_LOCK:
        if _LOGGING_INITIALIZED and not force:
            root_logger = logging.getLogger()
            if log_level is not None:
                numeric_level = getattr(logging, log_level.upper(), logging.INFO)
                root_logger.setLevel(numeric_level)
            return root_logger

        if log_level is None:
            log_level = config.LOG_LEVEL
        
        # Convert string to logging level
        numeric_level = getattr(logging, log_level.upper(), logging.INFO)
        
        # Create logs directory
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Generate log filename with timestamp
        log_filename = log_dir / f"hack_effect_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # Create formatter
        formatter = logging.Formatter(
            fmt=config.LOG_FORMAT,
            datefmt=config.LOG_DATE_FORMAT
        )
        
        # Setup root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)
        
        # Remove existing handlers safely
        for handler in list(root_logger.handlers):
            try:
                handler.close()
            except Exception:
                pass
        root_logger.handlers.clear()

        # The console stream is cp1252 on a default Windows install, so writing a
        # log record containing Thai text raised UnicodeEncodeError and silently
        # dropped the record. Force UTF-8 with a lossy fallback before attaching
        # the stream handler.
        for _stream in (sys.stdout, sys.stderr):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError, OSError):
                pass

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        # Last-resort guard: never let a record kill the emit loop.
        console_handler.handleError = lambda record: None
        root_logger.addHandler(console_handler)
        
        # File handler (optional)
        if log_to_file:
            file_handler = logging.FileHandler(log_filename, encoding='utf-8')
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        
        _LOGGING_INITIALIZED = True

        # Log startup message
        logging.info("=" * 60)
        logging.info("กดจนหลอนTone - Logging Initialized")
        logging.info(f"Log Level: {log_level}")
        logging.info(f"Log File: {log_filename if log_to_file else 'Disabled'}")
        logging.info("=" * 60)
        
        return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        logging.Logger: Configured logger instance
    """
    if not _LOGGING_INITIALIZED:
        setup_logging()
    return logging.getLogger(name)
