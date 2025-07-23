"""Core watermarking functionality."""

import os
import asyncio
from typing import Tuple, List, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import piexif
from datetime import datetime
import numpy as np
import requests

from ..utils.config import config


class WatermarkProcessor:
    """Main watermark processing class."""
    
    def __init__(self):
        """Initialize the watermark processor."""
        pass
    
    def convert_to_degrees(self, value: Tuple[Tuple[int, int], ...]) -> float:
        """Convert GPS coordinates from EXIF format to degrees."""
        d = float(value[0][0]) / float(value[0][1])
        m = float(value[1][0]) / float(value[1][1])
        s = float(value[2][0]) / float(value[2][1])
        return d + (m / 60.0) + (s / 3600.0)
    
    def get_location_string(self, exif_dict: dict) -> Optional[str]:
        """Extract GPS information from EXIF and format it."""
        try:
            gps_info = exif_dict.get('GPS', {})
            if not gps_info:
                return None

            lat_data = gps_info.get(piexif.GPSIFD.GPSLatitude)
            lon_data = gps_info.get(piexif.GPSIFD.GPSLongitude)
            lat_ref = gps_info.get(piexif.GPSIFD.GPSLatitudeRef)
            lon_ref = gps_info.get(piexif.GPSIFD.GPSLongitudeRef)

            if not all([lat_data, lon_data, lat_ref, lon_ref]):
                return None

            lat = self.convert_to_degrees(lat_data)
            lon = self.convert_to_degrees(lon_data)
            
            # Longitude first, latitude second, comma separated
            location_str = f"{lon},{lat}"
            print(f"Location string: {location_str}")
            
            if lat_ref == b'S':
                lat = -lat
            if lon_ref == b'W':
                lon = -lon
                
            formatted_location = f"{abs(lat):.6f}{'S' if lat < 0 else 'N'} {abs(lon):.6f}{'W' if lon < 0 else 'E'}"
            
            regeo_result = self.regeo_from_amap(location_str)
            
            if regeo_result['status'] == '1':
                # Get province, city, district information
                address_component = regeo_result.get('regeocode', {}).get('addressComponent', {})
                province = address_component.get('province', '')
                city = address_component.get('city', '')
                district = address_component.get('district', '')
                
                # If city is a list (empty case), convert to empty string
                if isinstance(city, list):
                    city = ''
                
                # Combine province, city, district, remove empty values
                location_parts = [part for part in [province, city, district] if part]
                return ''.join(location_parts) if location_parts else formatted_location
            else:
                return formatted_location

        except Exception as e:
            print(f"Error getting location: {e}")
            return None
    
    def regeo_from_amap(self, location_str: str) -> dict:
        """Get location information through coordinates using Amap API."""
        url = f"https://restapi.amap.com/v3/geocode/regeo?key={config.AMAP_API_KEY}&location={location_str}"
        try:
            response = requests.get(url, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Error calling Amap API: {e}")
            return {'status': '0'}
    
    def get_exif_info(self, img_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Get time and location information from EXIF."""
        try:
            exif_dict = piexif.load(img_path)
            # Get time
            dt_bytes = exif_dict['Exif'].get(piexif.ExifIFD.DateTimeOriginal)
            if dt_bytes:
                dt_str = dt_bytes.decode('utf-8')
                # EXIF format: 'YYYY:MM:DD HH:MM:SS'
                dt = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S').strftime('%Y-%m-%d  %H:%M:%S')
            else:
                dt = None
            
            # Get location
            location = self.get_location_string(exif_dict)
            
            return dt, location
        except Exception as e:
            print(f"Error reading EXIF: {e}")
            return None, None
    
    def get_jpeg_quality(self, img_path: str) -> Tuple[Optional[int], Optional[int]]:
        """Get JPEG image compression quality and chroma subsampling parameters."""
        try:
            with Image.open(img_path) as img:
                # 检查是否为JPEG格式
                if img.format != 'JPEG':
                    return None, None
                
                # 尝试访问量化表
                try:
                    qtables = getattr(img, 'quantization', None)
                    if not qtables:
                        return None, None
                except AttributeError:
                    return None, None
                
                # Estimate quality
                if len(qtables) >= 2:
                    # Has chroma quantization table, means 4:2:0 or 4:2:2 sampling
                    subsampling = 2  # 4:2:0
                else:
                    # Only luma quantization table, means 4:4:4 sampling
                    subsampling = 0  # 4:4:4
                
                # Estimate quality based on quantization table
                qsum = sum(sum(t) for t in qtables.values())
                qlen = sum(len(t) for t in qtables.values())
                quality = int(100 - (qsum / qlen) / 2)
                quality = max(1, min(100, quality))  # Ensure within 1-100 range
                
                return quality, subsampling
        except Exception as e:
            print(f"Cannot read compression parameters: {e}")
            return None, None
    
    def get_average_brightness(self, img: Image.Image, bbox: Tuple[int, int, int, int]) -> float:
        """Get average brightness of specified region."""
        region = img.crop(bbox)
        # Convert to grayscale
        if region.mode != 'L':
            region = region.convert('L')
        # Calculate average brightness
        return np.array(region).mean()
    
    def add_watermark(
        self, 
        img: Image.Image, 
        text_lines: List[str], 
        font_path: str, 
        location_font_path: str
    ) -> Image.Image:
        """Add watermark to image."""
        width, height = img.size
        # Use shortest side as base for font size
        base_size = min(width, height)
        
        # Create two fonts
        try:
            time_font = ImageFont.truetype(font_path, int(base_size * config.FONT_SIZE_RATIO))
        except OSError:
            print(f"Warning: Font file {font_path} not found, using default font")
            time_font = ImageFont.load_default()
            
        try:
            location_font = ImageFont.truetype(location_font_path, int(base_size * config.LOCATION_FONT_SIZE_RATIO))
        except OSError:
            print(f"Warning: Font file {location_font_path} not found, using default font")
            location_font = ImageFont.load_default()
        
        # Calculate maximum width and total height of all text lines
        draw = ImageDraw.Draw(img)
        max_text_w = 0
        total_text_h = 0
        line_heights = []
        
        # Calculate dimensions for each text line separately (using different fonts)
        for i, text in enumerate(text_lines):
            if not text:
                continue
            # First line uses time font, second line uses location font
            font = time_font if i == 0 else location_font
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            text_w = right - left
            text_h = bottom - top
            max_text_w = max(max_text_w, text_w)
            line_heights.append(text_h)
            total_text_h += text_h
        
        # Add line spacing
        if len(line_heights) > 1:
            total_text_h = int(total_text_h + (len(line_heights) - 1) * (base_size * config.FONT_SIZE_RATIO * (config.LINE_SPACING - 1)))
        
        # Calculate margins and padding (also based on shortest side)
        margin_x = int(base_size * config.MARGIN_RATIO)
        margin_y = int(base_size * config.MARGIN_RATIO)
        padding = int(base_size * config.PADDING_RATIO)
        
        # Calculate text box position (including padding)
        x = int(width - max_text_w - margin_x - padding * 2)
        y = int(height - total_text_h - margin_y - padding * 2)
        
        # Define text box region, expand blur area for soft edges
        blur_padding = padding * 2
        box_x0 = int(x - blur_padding)
        box_y0 = int(y - blur_padding)
        box_x1 = int(x + max_text_w + padding * 2 + blur_padding)
        box_y1 = int(y + total_text_h + padding * 2 + blur_padding)
        text_box = (box_x0, box_y0, box_x1, box_y1)
        
        # Extract background region and blur
        background = img.crop(text_box)
        blurred = background.filter(ImageFilter.GaussianBlur(config.BLUR_RADIUS))
        
        # Create gradient mask
        mask = Image.new('L', (box_x1 - box_x0, box_y1 - box_y0), 0)
        mask_draw = ImageDraw.Draw(mask)
        
        # Draw center rectangle (fully opaque)
        inner_box = (
            blur_padding,
            blur_padding,
            box_x1 - box_x0 - blur_padding,
            box_y1 - box_y0 - blur_padding
        )
        mask_draw.rectangle(inner_box, fill=255)
        
        # Apply Gaussian blur to mask to create soft edges
        mask = mask.filter(ImageFilter.GaussianBlur(blur_padding / 2))
        
        # Composite blurred background using mask
        img.paste(blurred, (box_x0, box_y0), mask)
        
        # Calculate region average brightness and choose text color
        brightness = self.get_average_brightness(img, (int(x), int(y), int(x + max_text_w + padding * 2), int(y + total_text_h + padding * 2)))
        text_color = (0, 0, 0, 255) if brightness > 128 else (255, 255, 255, 255)
        
        # Draw text (using unified padding)
        current_y = y + padding
        for i, text in enumerate(text_lines):
            if not text:
                continue
            # Choose corresponding font
            font = time_font if i == 0 else location_font
            # Calculate width of each text line for right alignment
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            text_w = right - left
            text_x = int(x + padding + (max_text_w - text_w))  # Right align
            
            draw.text((text_x, current_y), text, font=font, fill=text_color)
            if i < len(text_lines) - 1:  # Not last line
                current_y = int(current_y + line_heights[i] + (base_size * config.FONT_SIZE_RATIO * (config.LINE_SPACING - 1)))
        
        return img
    
    def process_single_image(
        self, 
        input_path: str, 
        output_path: str, 
        font_path: Optional[str] = None, 
        location_font_path: Optional[str] = None
    ) -> bool:
        """Process a single image."""
        try:
            font_path = font_path or config.FONT_PATH
            location_font_path = location_font_path or config.LOCATION_FONT_PATH
            
            # Read original EXIF information
            exif_dict = piexif.load(input_path)
            
            img = Image.open(input_path).convert('RGBA')
            dt, location = self.get_exif_info(input_path)
            
            if not dt:
                print(f"No timestamp found: {os.path.basename(input_path)}")
                return False
            
            # Prepare text lines
            text_lines = [dt]
            if location:
                text_lines.append(location)
            
            img = self.add_watermark(img, text_lines, font_path, location_font_path)
            
            # Maintain original format and high quality
            ext = os.path.splitext(input_path)[1].lower()
            if ext in ['.jpg', '.jpeg']:
                quality, subsampling = self.get_jpeg_quality(input_path)
                img = img.convert('RGB')
                
                # If unable to get original parameters, use default high quality settings
                if quality is None:
                    quality = config.DEFAULT_JPEG_QUALITY
                if subsampling is None:
                    subsampling = config.DEFAULT_JPEG_SUBSAMPLING
                    
                print(f"Using compression parameters - Quality: {quality}, Chroma subsampling: {subsampling} - {os.path.basename(input_path)}")
                
                # Convert EXIF to bytes
                exif_bytes = piexif.dump(exif_dict)
                
                # Save image with EXIF information
                img.save(output_path, 'JPEG', quality=quality, subsampling=subsampling, exif=exif_bytes)
            else:
                # PNG doesn't support EXIF, but we still save the image
                img.save(output_path, 'PNG')
                
            print(f"Processing completed: {os.path.basename(input_path)}")
            return True
            
        except Exception as e:
            print(f"Processing failed: {os.path.basename(input_path)}, Error: {e}")
            return False
    
    async def process_single_image_async(
        self, 
        input_path: str, 
        output_path: str, 
        font_path: Optional[str] = None, 
        location_font_path: Optional[str] = None
    ) -> bool:
        """Process a single image asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            self.process_single_image, 
            input_path, 
            output_path, 
            font_path, 
            location_font_path
        )
    
    def process_images_batch(
        self, 
        input_dir: str, 
        output_dir: str, 
        font_path: Optional[str] = None, 
        location_font_path: Optional[str] = None
    ) -> Tuple[int, int]:
        """Process images in batch."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        font_path = font_path or config.FONT_PATH
        location_font_path = location_font_path or config.LOCATION_FONT_PATH
        
        processed = 0
        failed = 0
        
        for fname in os.listdir(input_dir):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in config.IMAGE_EXTS:
                continue
                
            input_path = os.path.join(input_dir, fname)
            output_path = os.path.join(output_dir, fname)
            
            if self.process_single_image(input_path, output_path, font_path, location_font_path):
                processed += 1
            else:
                failed += 1
        
        return processed, failed
    
    async def process_images_batch_async(
        self, 
        input_dir: str, 
        output_dir: str, 
        font_path: Optional[str] = None, 
        location_font_path: Optional[str] = None,
        max_concurrent: int = 4
    ) -> Tuple[int, int]:
        """Process images in batch asynchronously."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        font_path = font_path or config.FONT_PATH
        location_font_path = location_font_path or config.LOCATION_FONT_PATH
        
        # Get all image files
        image_files = []
        for fname in os.listdir(input_dir):
            ext = os.path.splitext(fname)[1].lower()
            if ext in config.IMAGE_EXTS:
                input_path = os.path.join(input_dir, fname)
                output_path = os.path.join(output_dir, fname)
                image_files.append((input_path, output_path))
        
        processed = 0
        failed = 0
        
        # Process images with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(input_path: str, output_path: str) -> bool:
            async with semaphore:
                return await self.process_single_image_async(input_path, output_path, font_path, location_font_path)
        
        tasks = [process_with_semaphore(input_path, output_path) for input_path, output_path in image_files]
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result:
                processed += 1
            else:
                failed += 1
        
        return processed, failed
