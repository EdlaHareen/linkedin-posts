"""
Logging configuration for Newsletter to LinkedIn Post Automation.

Sets up console and file handlers with JSON formatting, log rotation,
and appropriate log levels for different environments.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.utils.logger import JsonFormatter


# Log directory configuration
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "pipeline.log"

# Ensure log directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging(
    console_level: str = "INFO",
    file_level: str = "DEBUG",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> None:
    """
    Configure logging for the application.
    
    Sets up:
    - Console handler with JSON formatting (INFO+)
    - Rotating file handler with JSON formatting (DEBUG+)
    - Log rotation at 10MB with 5 backups
    
    Args:
        console_level: Minimum level for console output (default: INFO)
        file_level: Minimum level for file output (default: DEBUG)
        max_bytes: Maximum size per log file before rotation (default: 10MB)
        backup_count: Number of backup files to keep (default: 5)
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything, filter at handler level
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Create JSON formatter
    json_formatter = JsonFormatter()
    
    # Console handler (INFO and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, console_level.upper()))
    console_handler.setFormatter(json_formatter)
    root_logger.addHandler(console_handler)
    
    # Rotating file handler (DEBUG and above)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, file_level.upper()))
    file_handler.setFormatter(json_formatter)
    root_logger.addHandler(file_handler)
    
    # Log initial configuration
    logger = logging.getLogger("newsletter_pipeline")
    logger.info(
        "Logging configured",
        extra={
            "step": "logging_init",
            "status": "success",
            "metadata": {
                "console_level": console_level,
                "file_level": file_level,
                "log_file": str(LOG_FILE),
                "max_bytes": max_bytes,
                "backup_count": backup_count
            }
        }
    )


def configure_logging_from_env() -> None:
    """
    Configure logging using environment variables.
    
    Environment variables:
    - LOG_CONSOLE_LEVEL: Console log level (default: INFO)
    - LOG_FILE_LEVEL: File log level (default: DEBUG)
    - LOG_MAX_BYTES: Max bytes per file (default: 10485760)
    - LOG_BACKUP_COUNT: Number of backups (default: 5)
    """
    console_level = os.getenv("LOG_CONSOLE_LEVEL", "INFO")
    file_level = os.getenv("LOG_FILE_LEVEL", "DEBUG")
    max_bytes = int(os.getenv("LOG_MAX_BYTES", "10485760"))
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    configure_logging(
        console_level=console_level,
        file_level=file_level,
        max_bytes=max_bytes,
        backup_count=backup_count
    )


# Configure logging on module import (can be overridden later)
if os.getenv("SKIP_LOGGING_CONFIG") != "true":
    configure_logging_from_env()
