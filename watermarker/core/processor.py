"""Image metadata extraction and watermark rendering."""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Iterable

import piexif
import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat, JpegImagePlugin

from ..utils.config import config


STYLE_PRESETS: dict[str, dict[str, object]] = {
    "minimal": {"plate_alpha": 72, "blur_scale": 0.7, "radius": 0.25, "stroke": 1},
    "glass": {"plate_alpha": 132, "blur_scale": 1.4, "radius": 0.8, "stroke": 1},
    "film": {"plate_alpha": 190, "blur_scale": 0.3, "radius": 0.0, "stroke": 0},
    "stamp": {"plate_alpha": 0, "blur_scale": 0.0, "radius": 0.0, "stroke": 2},
}
POSITIONS = ("auto", "top-left", "top-right", "bottom-left", "bottom-right")


@dataclass(slots=True)
class PhotoMetadata:
    captured_at: datetime | None = None
    time_source: str = ""
    latitude: float | None = None
    longitude: float | None = None
    location: str | None = None
    camera: str | None = None
    lens: str | None = None
    width: int = 0
    height: int = 0
    image_format: str = ""

    def as_dict(self) -> dict[str, object | None]:
        return {
            "captured_at": self.captured_at.isoformat(sep=" ") if self.captured_at else None,
            "time_source": self.time_source or None,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "location": self.location,
            "camera": self.camera,
            "lens": self.lens,
            "width": self.width,
            "height": self.height,
            "format": self.image_format,
        }


@dataclass(slots=True)
class WatermarkOptions:
    style: str = config.DEFAULT_STYLE
    position: str = config.DEFAULT_POSITION
    fields: tuple[str, ...] = ("time", "location")
    date_format: str = "%Y-%m-%d  %H:%M:%S"
    opacity: float = config.WATERMARK_OPACITY
    scale: float = 1.0
    custom_time: str | None = None
    custom_location: str | None = None
    geocode: bool = True
    quality: int | None = None
    max_dimension: int | None = None

    def __post_init__(self) -> None:
        if self.style not in STYLE_PRESETS:
            raise ValueError(f"Unknown style: {self.style}")
        if self.position not in POSITIONS:
            raise ValueError(f"Unknown position: {self.position}")
        self.opacity = max(0.0, min(1.0, self.opacity))
        self.scale = max(0.4, min(3.0, self.scale))
        if self.quality is not None:
            self.quality = max(1, min(100, self.quality))


@dataclass(slots=True)
class ProcessResult:
    input_path: Path
    output_path: Path | None = None
    success: bool = False
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object | None]:
        return {
            "input": str(self.input_path),
            "output": str(self.output_path) if self.output_path else None,
            "success": self.success,
            "error": self.error,
            "warnings": self.warnings,
        }


class WatermarkProcessor:
    """Extract metadata, render a selected style, and save safely."""

    def __init__(self) -> None:
        self._geocode_cache: dict[tuple[float, float], str | None] = {}
        self._cache_lock = Lock()

    @staticmethod
    def _decode(value: object) -> str | None:
        if not value:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip("\x00 ") or None
        return str(value).strip() or None

    @staticmethod
    def _rational(value: object) -> float:
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            return float(value.numerator) / float(value.denominator)
        numerator, denominator = value  # type: ignore[misc]
        return float(numerator) / float(denominator)

    def convert_to_degrees(self, value: Iterable[object]) -> float:
        degrees, minutes, seconds = list(value)
        return self._rational(degrees) + self._rational(minutes) / 60 + self._rational(seconds) / 3600

    @staticmethod
    def _parse_exif_datetime(value: object) -> datetime | None:
        text = WatermarkProcessor._decode(value)
        if not text:
            return None
        for pattern in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                continue
        return None

    def _coordinates(self, exif_dict: dict) -> tuple[float | None, float | None]:
        gps = exif_dict.get("GPS", {})
        try:
            latitude = self.convert_to_degrees(gps[piexif.GPSIFD.GPSLatitude])
            longitude = self.convert_to_degrees(gps[piexif.GPSIFD.GPSLongitude])
            if gps.get(piexif.GPSIFD.GPSLatitudeRef) == b"S":
                latitude = -latitude
            if gps.get(piexif.GPSIFD.GPSLongitudeRef) == b"W":
                longitude = -longitude
            return latitude, longitude
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None, None

    @staticmethod
    def _coordinate_label(latitude: float, longitude: float) -> str:
        return (
            f"{abs(latitude):.6f}{'S' if latitude < 0 else 'N'} "
            f"{abs(longitude):.6f}{'W' if longitude < 0 else 'E'}"
        )

    def reverse_geocode(self, latitude: float, longitude: float) -> str | None:
        """Resolve GPS coordinates, with a process-local cache and coordinate fallback."""
        if not config.AMAP_API_KEY:
            return None
        cache_key = (round(latitude, 5), round(longitude, 5))
        with self._cache_lock:
            if cache_key in self._geocode_cache:
                return self._geocode_cache[cache_key]
        try:
            response = requests.get(
                "https://restapi.amap.com/v3/geocode/regeo",
                params={
                    "key": config.AMAP_API_KEY,
                    "location": f"{longitude},{latitude}",
                    "coordsys": "gps",
                    "extensions": "base",
                },
                timeout=(3, 8),
            )
            response.raise_for_status()
            payload = response.json()
            component = payload.get("regeocode", {}).get("addressComponent", {})
            parts: list[str] = []
            for key in ("province", "city", "district"):
                value = component.get(key, "")
                if isinstance(value, str) and value and value not in parts:
                    parts.append(value)
            location = "".join(parts) or None
        except (requests.RequestException, ValueError, TypeError):
            location = None
        with self._cache_lock:
            self._geocode_cache[cache_key] = location
        return location

    def inspect_image(self, image_path: str | Path, geocode: bool = True) -> PhotoMetadata:
        path = Path(image_path)
        with Image.open(path) as image:
            width, height = ImageOps.exif_transpose(image).size
            image_format = image.format or path.suffix.lstrip(".").upper()
        try:
            exif = piexif.load(str(path))
        except (ValueError, piexif.InvalidImageDataError):
            exif = {"0th": {}, "Exif": {}, "GPS": {}}

        zeroth = exif.get("0th", {})
        details = exif.get("Exif", {})
        captured_at = None
        time_source = ""
        for source, value in (
            ("DateTimeOriginal", details.get(piexif.ExifIFD.DateTimeOriginal)),
            ("DateTimeDigitized", details.get(piexif.ExifIFD.DateTimeDigitized)),
            ("DateTime", zeroth.get(piexif.ImageIFD.DateTime)),
        ):
            captured_at = self._parse_exif_datetime(value)
            if captured_at:
                time_source = source
                break
        if captured_at is None:
            captured_at = datetime.fromtimestamp(path.stat().st_mtime)
            time_source = "file_mtime"

        latitude, longitude = self._coordinates(exif)
        location = None
        if latitude is not None and longitude is not None:
            if geocode:
                location = self.reverse_geocode(latitude, longitude)
            location = location or self._coordinate_label(latitude, longitude)

        make = self._decode(zeroth.get(piexif.ImageIFD.Make))
        model = self._decode(zeroth.get(piexif.ImageIFD.Model))
        camera = " ".join(part for part in (make, model) if part)
        if make and model and model.lower().startswith(make.lower()):
            camera = model
        lens = self._decode(details.get(piexif.ExifIFD.LensModel))
        return PhotoMetadata(
            captured_at=captured_at,
            time_source=time_source,
            latitude=latitude,
            longitude=longitude,
            location=location,
            camera=camera or None,
            lens=lens,
            width=width,
            height=height,
            image_format=image_format,
        )

    @staticmethod
    def _font_candidates(configured: str, bold: bool = False) -> list[str]:
        candidates = [configured] if configured else []
        candidates.extend(
            [
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            ]
        )
        return candidates

    def _load_font(self, configured: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for candidate in self._font_candidates(configured, bold):
            try:
                return ImageFont.truetype(candidate, max(8, size))
            except OSError:
                continue
        return ImageFont.load_default(size=max(8, size))

    @staticmethod
    def _brightness(image: Image.Image, box: tuple[int, int, int, int]) -> float:
        return ImageStat.Stat(image.crop(box).convert("L")).mean[0]

    @staticmethod
    def _position_box(
        position: str,
        canvas: tuple[int, int],
        size: tuple[int, int],
        margin: int,
    ) -> tuple[int, int, int, int]:
        width, height = canvas
        box_width, box_height = size
        left = margin if position.endswith("left") else width - margin - box_width
        top = margin if position.startswith("top") else height - margin - box_height
        return left, top, left + box_width, top + box_height

    def _auto_position(
        self,
        image: Image.Image,
        size: tuple[int, int],
        margin: int,
    ) -> str:
        scored: list[tuple[float, str]] = []
        preferences = {"bottom-right": 0.0, "bottom-left": 1.0, "top-right": 2.0, "top-left": 3.0}
        for position in preferences:
            box = self._position_box(position, image.size, size, margin)
            region = image.crop(box).convert("L")
            variance = ImageStat.Stat(region).var[0]
            edge_mean = ImageStat.Stat(region.filter(ImageFilter.FIND_EDGES)).mean[0]
            scored.append((variance + edge_mean * 2 + preferences[position], position))
        return min(scored)[1]

    @staticmethod
    def _field_lines(metadata: PhotoMetadata, options: WatermarkOptions) -> list[tuple[str, str]]:
        values = {
            "time": options.custom_time
            or (metadata.captured_at.strftime(options.date_format) if metadata.captured_at else None),
            "location": options.custom_location or metadata.location,
            "camera": metadata.camera,
            "lens": metadata.lens,
        }
        return [(field_name, values[field_name]) for field_name in options.fields if values.get(field_name)]  # type: ignore[list-item]

    def add_watermark(
        self,
        image: Image.Image,
        metadata: PhotoMetadata,
        options: WatermarkOptions,
    ) -> Image.Image:
        """Render a style preset on an RGBA image."""
        lines = self._field_lines(metadata, options)
        if not lines:
            raise ValueError("No requested watermark fields are available")

        preset = STYLE_PRESETS[options.style]
        base = min(image.size)
        time_size = int(base * config.FONT_SIZE_RATIO * options.scale)
        detail_size = int(base * config.LOCATION_FONT_SIZE_RATIO * options.scale)
        fonts = {
            field_name: self._load_font(
                config.FONT_PATH if field_name == "time" else config.LOCATION_FONT_PATH,
                time_size if field_name == "time" else detail_size,
                bold=field_name == "time" and options.style != "stamp",
            )
            for field_name, _ in lines
        }
        measure = ImageDraw.Draw(image)
        metrics: list[tuple[str, str, ImageFont.ImageFont, int, int]] = []
        max_width = 0
        gap = max(2, int(detail_size * (config.LINE_SPACING - 0.6)))
        for field_name, text in lines:
            font = fonts[field_name]
            left, top, right, bottom = measure.textbbox((0, 0), text, font=font, anchor="lt")
            text_width, text_height = right - left, bottom - top
            metrics.append((field_name, text, font, text_width, text_height))
            max_width = max(max_width, text_width)

        padding = max(6, int(base * config.PADDING_RATIO * options.scale))
        margin = max(8, int(base * config.MARGIN_RATIO))
        available_width = max(40, image.width - margin * 2 - padding * 2)
        if max_width > available_width:
            fit = available_width / max_width
            metrics = []
            max_width = 0
            for field_name, text in lines:
                original_size = time_size if field_name == "time" else detail_size
                font = self._load_font(
                    config.FONT_PATH if field_name == "time" else config.LOCATION_FONT_PATH,
                    int(original_size * fit),
                    bold=field_name == "time" and options.style != "stamp",
                )
                left, top, right, bottom = measure.textbbox((0, 0), text, font=font, anchor="lt")
                text_width, text_height = right - left, bottom - top
                metrics.append((field_name, text, font, text_width, text_height))
                max_width = max(max_width, text_width)
        content_height = sum(item[4] for item in metrics) + gap * (len(metrics) - 1)
        box_size = (max_width + padding * 2, content_height + padding * 2)
        position = options.position
        if position == "auto":
            position = self._auto_position(image, box_size, margin)
        box = self._position_box(position, image.size, box_size, margin)
        box = (
            max(0, box[0]),
            max(0, box[1]),
            min(image.width, box[2]),
            min(image.height, box[3]),
        )

        brightness = self._brightness(image, box)
        foreground = (18, 18, 18, 255) if brightness > 145 else (248, 248, 248, 255)
        plate_rgb = (255, 255, 255) if brightness > 145 else (0, 0, 0)
        opacity = options.opacity
        plate_alpha = int(int(preset["plate_alpha"]) * opacity)
        blur_radius = int(config.BLUR_RADIUS * float(preset["blur_scale"]) * max(1, base / 2000))
        radius = int(padding * float(preset["radius"]))

        result = image.convert("RGBA")
        if blur_radius > 0:
            blurred = result.crop(box).filter(ImageFilter.GaussianBlur(blur_radius))
            mask = Image.new("L", blurred.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, *blurred.size), radius=radius, fill=255)
            result.paste(blurred, box[:2], mask)
        if plate_alpha > 0:
            plate = Image.new("RGBA", result.size, (0, 0, 0, 0))
            ImageDraw.Draw(plate).rounded_rectangle(
                box,
                radius=radius,
                fill=(*plate_rgb, plate_alpha),
            )
            result = Image.alpha_composite(result, plate)

        draw = ImageDraw.Draw(result)
        current_y = box[1] + padding
        stroke = int(preset["stroke"])
        stroke_fill = (255, 255, 255, 150) if foreground[0] < 128 else (0, 0, 0, 150)
        align_right = position.endswith("right")
        for _, text, font, text_width, text_height in metrics:
            text_x = box[2] - padding - text_width if align_right else box[0] + padding
            draw.text(
                (text_x, current_y),
                text,
                font=font,
                fill=foreground,
                anchor="lt",
                stroke_width=stroke,
                stroke_fill=stroke_fill,
            )
            current_y += text_height + gap
        return result

    def process_single_image_detailed(
        self,
        input_path: str | Path,
        output_path: str | Path,
        options: WatermarkOptions | None = None,
    ) -> ProcessResult:
        source = Path(input_path)
        destination = Path(output_path)
        result = ProcessResult(input_path=source, output_path=destination)
        options = options or WatermarkOptions()
        temporary: Path | None = None
        try:
            if not source.is_file():
                raise FileNotFoundError(f"Input file does not exist: {source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() == destination.resolve():
                raise ValueError("Input and output paths must be different")

            metadata = self.inspect_image(source, geocode=options.geocode)
            try:
                exif_dict = piexif.load(str(source))
            except (ValueError, piexif.InvalidImageDataError):
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

            with Image.open(source) as original:
                source_format = original.format or source.suffix.lstrip(".").upper()
                info = dict(original.info)
                qtables = getattr(original, "quantization", None)
                sampling = JpegImagePlugin.get_sampling(original) if source_format == "JPEG" else None
                image = ImageOps.exif_transpose(original).convert("RGBA")
            if options.max_dimension and max(image.size) > options.max_dimension:
                image.thumbnail((options.max_dimension, options.max_dimension), Image.Resampling.LANCZOS)
            image = self.add_watermark(image, metadata, options)

            exif_dict.setdefault("0th", {}).pop(piexif.ImageIFD.Orientation, None)
            exif_bytes = piexif.dump(exif_dict)
            suffix = destination.suffix.lower() or source.suffix.lower()
            with tempfile.NamedTemporaryFile(
                prefix=f".{destination.stem}.", suffix=suffix, dir=destination.parent, delete=False
            ) as handle:
                temporary = Path(handle.name)

            save_kwargs: dict[str, object] = {}
            if info.get("icc_profile"):
                save_kwargs["icc_profile"] = info["icc_profile"]
            if info.get("dpi"):
                save_kwargs["dpi"] = info["dpi"]
            if suffix in {".jpg", ".jpeg"}:
                image = image.convert("RGB")
                save_kwargs["exif"] = exif_bytes
                if options.quality is not None or not qtables:
                    save_kwargs["quality"] = options.quality or config.DEFAULT_JPEG_QUALITY
                    save_kwargs["subsampling"] = config.DEFAULT_JPEG_SUBSAMPLING
                else:
                    save_kwargs["qtables"] = qtables
                    if sampling is not None:
                        save_kwargs["subsampling"] = sampling
                image.save(temporary, "JPEG", **save_kwargs)
            elif suffix == ".webp":
                save_kwargs["exif"] = exif_bytes
                image.save(temporary, "WEBP", quality=options.quality or config.DEFAULT_JPEG_QUALITY, **save_kwargs)
            else:
                save_kwargs["exif"] = exif_bytes
                image.save(temporary, "PNG", **save_kwargs)
            os.replace(temporary, destination)
            temporary = None
            result.success = True
        except Exception as exc:
            result.error = str(exc)
        finally:
            if temporary and temporary.exists():
                temporary.unlink(missing_ok=True)
        return result

    def process_single_image(
        self,
        input_path: str,
        output_path: str,
        font_path: str | None = None,
        location_font_path: str | None = None,
    ) -> bool:
        """Compatibility wrapper used by the HTTP server."""
        return self.process_single_image_detailed(input_path, output_path).success

    async def process_single_image_async(
        self,
        input_path: str,
        output_path: str,
        font_path: str | None = None,
        location_font_path: str | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self.process_single_image,
            input_path,
            output_path,
            font_path,
            location_font_path,
        )
