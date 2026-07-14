"""Configuration management without import-time console noise."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


class Config:
    """Load defaults from environment variables and an optional dotenv file."""

    def __init__(self) -> None:
        self.env_file = self._load_env_file()
        self._setup_default_values()

    @staticmethod
    def _load_env_file() -> Path | None:
        explicit = os.getenv("WATERMARK_CONFIG")
        candidates = [Path(explicit)] if explicit else [Path(".env.local"), Path(".env")]
        for candidate in candidates:
            if candidate.is_file():
                load_dotenv(candidate, override=False)
                return candidate.resolve()
        return None

    @staticmethod
    def get_env_float(key: str, default: float) -> float:
        try:
            return float(os.environ.get(key, default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_env_str(key: str, default: str) -> str:
        return os.getenv(key, default)

    @staticmethod
    def get_env_int(key: str, default: int) -> int:
        try:
            return int(os.environ.get(key, default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_env_bool(key: str, default: bool) -> bool:
        value = os.getenv(key)
        if value is None:
            return default
        return value.strip().lower() in {"true", "1", "yes", "on"}

    def _setup_default_values(self) -> None:
        self.INPUT_DIR = self.get_env_str("WATERMARK_INPUT_DIR", "input")
        self.OUTPUT_DIR = self.get_env_str("WATERMARK_OUTPUT_DIR", "output")

        self.FONT_PATH = self.get_env_str("WATERMARK_TIME_FONT_PATH", "")
        self.LOCATION_FONT_PATH = self.get_env_str("WATERMARK_LOCATION_FONT_PATH", "")
        self.FONT_SIZE_RATIO = self.get_env_float("WATERMARK_TIME_FONT_SIZE_RATIO", 0.035)
        self.LOCATION_FONT_SIZE_RATIO = self.get_env_float("WATERMARK_LOCATION_FONT_SIZE_RATIO", 0.022)
        self.MARGIN_RATIO = self.get_env_float("WATERMARK_MARGIN_RATIO", 0.025)
        self.PADDING_RATIO = self.get_env_float("WATERMARK_PADDING_RATIO", 0.012)
        self.LINE_SPACING = self.get_env_float("WATERMARK_LINE_SPACING", 1.25)
        self.BLUR_RADIUS = self.get_env_int("WATERMARK_BLUR_RADIUS", 14)
        self.WATERMARK_OPACITY = self.get_env_float("WATERMARK_OPACITY", 0.88)
        self.DEFAULT_STYLE = self.get_env_str("WATERMARK_STYLE", "minimal")
        self.DEFAULT_POSITION = self.get_env_str("WATERMARK_POSITION", "auto")

        raw_exts = self.get_env_str("WATERMARK_IMAGE_EXTS", ".jpg,.jpeg,.png,.webp")
        self.IMAGE_EXTS = tuple(
            ext if ext.startswith(".") else f".{ext}"
            for item in raw_exts.split(",")
            if (ext := item.strip().lower())
        )
        self.DEFAULT_JPEG_QUALITY = max(
            1, min(100, self.get_env_int("WATERMARK_DEFAULT_JPEG_QUALITY", 95))
        )
        self.DEFAULT_JPEG_SUBSAMPLING = self.get_env_int(
            "WATERMARK_DEFAULT_JPEG_SUBSAMPLING", 0
        )

        self.AMAP_API_KEY = self.get_env_str("WATERMARK_AMAP_API_KEY", "")
        self.API_TOKEN = self.get_env_str("WATERMARK_API_TOKEN", "")
        self.SERVER_HOST = self.get_env_str("WATERMARK_SERVER_HOST", "127.0.0.1")
        self.SERVER_PORT = self.get_env_int("WATERMARK_SERVER_PORT", 9393)
        self.DEBUG = self.get_env_bool("WATERMARK_DEBUG", False)
        self.LOG_LEVEL = self.get_env_str("WATERMARK_LOG_LEVEL", "INFO")
        self.LOG_FILE = self.get_env_str("WATERMARK_LOG_FILE", "logs/watermarker.log")

    def as_dict(self) -> dict[str, object]:
        """Return public settings for CLI display."""
        return {
            key: value
            for key, value in vars(self).items()
            if key.isupper() or key == "env_file"
        }


config = Config()
