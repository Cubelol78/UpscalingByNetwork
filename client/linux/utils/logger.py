"""
Logging configuration for the Linux client
Cross-platform logging with file rotation and structured output
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for terminal output"""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, fmt: str, use_colors: bool = True):
        super().__init__(fmt)
        self.use_colors = use_colors and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        if self.use_colors:
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = (
                    f"{self.COLORS[levelname]}{levelname}{self.RESET}"
                )
        return super().format(record)


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[Path] = None,
    log_file: str = "client.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    use_colors: bool = True,
) -> logging.Logger:
    """
    Configure logging for the client

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files (uses XDG_DATA_HOME if None)
        log_file: Name of the log file
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
        use_colors: Use colored output for console

    Returns:
        Configured root logger
    """
    # Determine log directory
    if log_dir is None:
        # Use XDG base directory specification on Linux
        xdg_data_home = Path.home() / ".local" / "share"
        log_dir = xdg_data_home / "upscaling-client" / "logs"

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Convert log level string to logging level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create formatters
    detailed_format = (
        "%(asctime)s - %(name)s - %(levelname)s - "
        "%(filename)s:%(lineno)d - %(message)s"
    )
    simple_format = "%(asctime)s - %(levelname)s - %(message)s"

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_formatter = ColoredFormatter(simple_format, use_colors=use_colors)
    console_handler.setFormatter(console_formatter)

    # File handler with rotation
    log_file_path = log_dir / log_file
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # Always log everything to file
    file_formatter = logging.Formatter(detailed_format)
    file_handler.setFormatter(file_formatter)

    # Error file handler (errors and critical only)
    error_file_path = log_dir / "errors.log"
    error_handler = RotatingFileHandler(
        error_file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add our handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)

    # Log startup info
    logger = logging.getLogger(__name__)
    logger.info("=" * 70)
    logger.info(f"Logging initialized - Level: {log_level}")
    logger.info(f"Log directory: {log_dir}")
    logger.info(f"Log file: {log_file_path}")
    logger.info("=" * 70)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module

    Args:
        name: Name of the module (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for temporary log level changes"""

    def __init__(self, logger: logging.Logger, level: int):
        self.logger = logger
        self.new_level = level
        self.old_level = None

    def __enter__(self):
        self.old_level = self.logger.level
        self.logger.setLevel(self.new_level)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.setLevel(self.old_level)


def log_function_call(func):
    """Decorator to log function calls with arguments and return values"""

    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")

        try:
            result = func(*args, **kwargs)
            logger.debug(f"{func.__name__} returned: {result}")
            return result
        except Exception as e:
            logger.exception(f"Exception in {func.__name__}: {e}")
            raise

    return wrapper
