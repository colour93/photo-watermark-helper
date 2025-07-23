"""File and image utilities."""

import os
import base64
import io
import asyncio
from typing import Optional, Union
from pathlib import Path
from functools import partial

import aiofiles
from fastapi import UploadFile
from PIL import Image


def ensure_directory(directory: Union[str, Path]) -> None:
    """Ensure a directory exists, creating it if necessary."""
    Path(directory).mkdir(parents=True, exist_ok=True)


def image_to_base64(image: Union[str, Path, Image.Image], format: str = "") -> str:
    """
    Convert an image to a base64 string.
    
    Args:
        image: Path to an image file or PIL Image object
        format: Optional format override (png, jpeg, etc.)
        
    Returns:
        Base64 encoded string of the image
    """
    img_obj = None
    
    try:
        if isinstance(image, (str, Path)):
            img_obj = Image.open(image)
        elif isinstance(image, Image.Image):
            img_obj = image
        else:
            raise ValueError("Image must be a file path or PIL Image object")
        
        # If no format specified, use original or default to PNG
        if format is None:
            if isinstance(image, (str, Path)):
                ext = os.path.splitext(str(image))[1].lower()
                format = ext[1:] if ext else 'png'  # Remove the dot
            else:
                format = img_obj.format.lower() if img_obj.format else 'png'
        
        # Make sure format is lowercase
        format = format.lower()
        
        # Convert to RGB if saving as JPEG
        if format in ('jpg', 'jpeg') and img_obj.mode == 'RGBA':
            img_obj = img_obj.convert('RGB')
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        img_obj.save(buffer, format=format)
        buffer.seek(0)
        
        # Encode to base64
        img_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return img_b64
    
    finally:
        # Close image only if we opened it
        if img_obj and isinstance(image, (str, Path)):
            img_obj.close()


def base64_to_image(b64_string: str, output_path: Optional[str] = None) -> Optional[Image.Image]:
    """
    Convert a base64 string to a PIL Image or save it to a file.
    
    Args:
        b64_string: Base64 encoded image string
        output_path: Optional path to save the image to
        
    Returns:
        PIL Image object if output_path is None, otherwise None
    """
    try:
        # Check if string is empty or None
        if not b64_string:
            raise ValueError("Empty base64 string provided")
        
        # Remove data URL prefix if present
        if ',' in b64_string:
            mime_type, b64_string = b64_string.split(',', 1)
            # Log the mime type for debugging
            print(f"Detected MIME type: {mime_type}")
        
        # Decode base64
        try:
            img_data = base64.b64decode(b64_string)
        except Exception as e:
            raise ValueError(f"Invalid base64 encoding: {str(e)}")
        
        if len(img_data) == 0:
            raise ValueError("Decoded base64 data is empty")
        
        # Create PIL Image
        try:
            img = Image.open(io.BytesIO(img_data))
            print(f"Image format: {img.format}, mode: {img.mode}, size: {img.size}")
        except Exception as e:
            raise ValueError(f"Cannot open image data: {str(e)}")
        
        # Save to file if path provided
        if output_path:
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            
            # Determine format from extension
            ext = os.path.splitext(output_path)[1].lower()
            format = ext[1:].upper() if ext else (img.format if img.format else 'PNG')
            
            # Convert to RGB if saving as JPEG
            if format.lower() in ('jpg', 'jpeg') and img.mode == 'RGBA':
                print("Converting RGBA image to RGB for JPEG format")
                img = img.convert('RGB')
            
            print(f"Saving image as {format} to {output_path}")
            with open(output_path, 'wb') as out_file:
                img.save(out_file, format=format)
            img.show()  # Show the image if needed
            img.close()
            return None
        
        return img
    
    except Exception as e:
        print(f"Error converting base64 to image: {e}")
        raise  # Re-raise the exception to propagate it to the caller


def get_image_format(image_path: Union[str, Path]) -> str:
    """
    Get the format of an image file.
    
    Args:
        image_path: Path to an image file
        
    Returns:
        Format of the image (e.g., 'JPEG', 'PNG')
    """
    try:
        with Image.open(image_path) as img:
            return img.format if img.format else ""
    except Exception as e:
        print(f"Error getting image format: {e}")
        return ""


def get_temp_filepath(prefix: str = "watermark_", suffix: str = ".jpg") -> str:
    """
    Generate a temporary file path within the project directory.
    
    Args:
        prefix: Prefix for the filename
        suffix: Suffix (extension) for the filename
        
    Returns:
        Temporary file path
    """
    import uuid
    from pathlib import Path
    
    # 在项目根目录创建tmp文件夹
    project_root = Path(__file__).parents[2]  # 向上三级到项目根目录
    temp_dir = project_root / "tmp"
    
    # 确保目录存在
    os.makedirs(temp_dir, exist_ok=True)
    
    # 生成唯一文件名
    filename = f"{prefix}{uuid.uuid4().hex[:8]}{suffix}"
    temp_path = temp_dir / filename
    
    print(f"Created temp file path: {temp_path}")
    return str(temp_path)


async def async_image_to_base64(image_path: Union[str, Path]) -> str:
    """
    Asynchronously convert an image to base64 string using asyncio.to_thread.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Base64 encoded string of the image
    """
    func = partial(image_to_base64, image_path)
    return await asyncio.to_thread(func)


async def async_base64_to_image(b64_string: str, output_path: str) -> bool:
    """
    Asynchronously convert a base64 string to an image and save it.
    
    Args:
        b64_string: Base64 encoded image string
        output_path: Path to save the image to
        
    Returns:
        True if successful, False otherwise
    """
    try:
        func = partial(base64_to_image, b64_string, output_path)
        await asyncio.to_thread(func)
        return True
    except Exception as e:
        print(f"Error in async_base64_to_image: {e}")
        return False


async def async_save_uploaded_file(upload_file: Union[bytes, UploadFile], destination_path: str) -> bool:
    """
    Asynchronously save an uploaded file to disk.
    
    Args:
        upload_file: File content as bytes or UploadFile object
        destination_path: Where to save the file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
        
        # Handle different input types
        if isinstance(upload_file, bytes):
            # Direct bytes content
            async with aiofiles.open(destination_path, 'wb') as f:
                await f.write(upload_file)
        elif isinstance(upload_file, UploadFile):
            # FastAPI's UploadFile object
            # Read the content first to avoid blocking
            content = await upload_file.read()
            # Then write it using async file I/O
            async with aiofiles.open(destination_path, 'wb') as f:
                await f.write(content)
        else:
            # Unsupported type
            raise TypeError("upload_file must be bytes or UploadFile")
        
        return True
    except Exception as e:
        print(f"Error saving uploaded file: {e}")
        return False
