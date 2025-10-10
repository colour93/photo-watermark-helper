"""Configuration management."""

import os
from pathlib import Path
from dotenv import load_dotenv


class Config:
    """Configuration manager for watermark application."""
    
    def __init__(self):
        """Initialize configuration."""
        self.load_env_file()
        self._setup_default_values()
    
    def load_env_file(self) -> None:
        """
        Load environment variables in priority order:
        1. .env.local (if exists)
        2. .env
        """
        env_local = Path('.env.local')
        env_default = Path('.env')
        
        if env_local.exists():
            load_dotenv(env_local)
            print(f"Loaded config file: {env_local}")
        elif env_default.exists():
            load_dotenv(env_default)
            print(f"Loaded config file: {env_default}")
        else:
            print("No config file found, using default values")
    
    def get_env_float(self, key: str, default: float) -> float:
        """Get float environment variable."""
        value = os.getenv(key)
        try:
            return float(value) if value is not None else default
        except ValueError:
            print(f"Warning: Environment variable {key} value '{value}' cannot be converted to float, using default {default}")
            return default
    
    def get_env_str(self, key: str, default: str) -> str:
        """Get string environment variable."""
        return os.getenv(key, default)
    
    def get_env_int(self, key: str, default: int) -> int:
        """Get integer environment variable."""
        value = os.getenv(key)
        try:
            return int(value) if value is not None else default
        except ValueError:
            print(f"Warning: Environment variable {key} value '{value}' cannot be converted to integer, using default {default}")
            return default
    
    def get_env_bool(self, key: str, default: bool) -> bool:
        """Get boolean environment variable."""
        value = os.getenv(key)
        if value is None:
            return default
        return value.lower() in ('true', '1', 'yes', 'on')
    
    def _setup_default_values(self) -> None:
        """Setup default configuration values."""
        # Basic paths
        self.INPUT_DIR = self.get_env_str('WATERMARK_INPUT_DIR', 'input')
        self.OUTPUT_DIR = self.get_env_str('WATERMARK_OUTPUT_DIR', 'output')
        
        # Fonts
        self.FONT_PATH = self.get_env_str('WATERMARK_TIME_FONT_PATH', 'sarasa-mono-sc-semibold.ttf')
        self.LOCATION_FONT_PATH = self.get_env_str('WATERMARK_LOCATION_FONT_PATH', 'sarasa-mono-sc-semibold.ttf')
        
        # Font sizing
        self.FONT_SIZE_RATIO = self.get_env_float('WATERMARK_TIME_FONT_SIZE_RATIO', 0.04)
        self.LOCATION_FONT_SIZE_RATIO = self.get_env_float('WATERMARK_LOCATION_FONT_SIZE_RATIO', 0.03)
        
        # Layout
        self.MARGIN_RATIO = self.get_env_float('WATERMARK_MARGIN_RATIO', 0.02)
        self.PADDING_RATIO = self.get_env_float('WATERMARK_PADDING_RATIO', 0.01)
        self.LINE_SPACING = self.get_env_float('WATERMARK_LINE_SPACING', 1.5)
        
        # Effects
        self.BLUR_RADIUS = self.get_env_int('WATERMARK_BLUR_RADIUS', 10)
        
        # Image settings
        self.IMAGE_EXTS = self.get_env_str('WATERMARK_IMAGE_EXTS', '.jpg,.jpeg,.png').split(',')
        self.DEFAULT_JPEG_QUALITY = self.get_env_int('WATERMARK_DEFAULT_JPEG_QUALITY', 95)
        self.DEFAULT_JPEG_SUBSAMPLING = self.get_env_int('WATERMARK_DEFAULT_JPEG_SUBSAMPLING', 0)
        
        # API keys
        self.AMAP_API_KEY = self.get_env_str('WATERMARK_AMAP_API_KEY', 'xxx')
        self.API_TOKEN = self.get_env_str('WATERMARK_API_TOKEN', '')
        
        # Server settings
        self.SERVER_HOST = self.get_env_str('WATERMARK_SERVER_HOST', '0.0.0.0')
        self.SERVER_PORT = self.get_env_int('WATERMARK_SERVER_PORT', 8000)
        self.DEBUG = self.get_env_bool('WATERMARK_DEBUG', False)
        
        # Logging
        self.LOG_LEVEL = self.get_env_str('WATERMARK_LOG_LEVEL', 'INFO')
        self.LOG_FILE = self.get_env_str('WATERMARK_LOG_FILE', 'logs/watermarker.log')


# Global configuration instance
config = Config()
