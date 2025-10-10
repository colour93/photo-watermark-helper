"""Logging configuration and utilities."""

import sys
from pathlib import Path
from loguru import logger


def setup_logging(
    log_level: str = "INFO",
    log_file: str = "logs/watermarker.log",
    enable_file_logging: bool = True,
    enable_console_logging: bool = True
) -> None:
    """
    Setup logging configuration with loguru.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file path
        enable_file_logging: Whether to enable file logging
        enable_console_logging: Whether to enable console logging
    """
    # Remove default logger
    logger.remove()
    
    # Setup console logging
    if enable_console_logging:
        logger.add(
            sys.stderr,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                   "<level>{level: <8}</level> | "
                   "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                   "<level>{message}</level>",
            colorize=True
        )
    
    # Setup file logging
    if enable_file_logging and log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            log_file,
            level=log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="7 days",
            compression="gz",
            encoding="utf-8"
        )


def get_logger(name: str = __name__):
    """Get a logger instance."""
    return logger.bind(name=name)


# Setup default logging
setup_logging()
