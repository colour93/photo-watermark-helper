"""Main entry point for the watermarking application."""

import os
from loguru import logger

from .utils.config import config
from .utils.logger import setup_logging
from .cli.commands import cli


def init_app():
    """Initialize the application."""
    # Setup logging
    setup_logging(
        log_level=config.LOG_LEVEL,
        log_file=config.LOG_FILE
    )
    
    logger.info("Initializing Photo Watermark Helper")
    
    # Check if required directories exist
    if not os.path.exists(config.INPUT_DIR):
        logger.warning(f"Input directory does not exist: {config.INPUT_DIR}")
    
    if not os.path.exists(config.OUTPUT_DIR):
        logger.info(f"Creating output directory: {config.OUTPUT_DIR}")
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)


if __name__ == "__main__":
    init_app()
    cli()
