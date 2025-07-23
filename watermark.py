import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import piexif
from datetime import datetime
import numpy as np
import requests
from dotenv import load_dotenv
from pathlib import Path

# 自动加载环境变量
def load_env_file():
    """
    按以下顺序加载环境变量文件：
    1. .env.local（如果存在）
    2. .env
    """
    env_local = Path('.env.local')
    env_default = Path('.env')
    
    if env_local.exists():
        load_dotenv(env_local)
        print(f"已加载配置文件: {env_local}")
    elif env_default.exists():
        load_dotenv(env_default)
        print(f"已加载配置文件: {env_default}")
    else:
        print("未找到配置文件，使用默认值")

# 从环境变量获取配置，如果没有则使用默认值
def get_env_float(key, default):
    """获取浮点型环境变量"""
    value = os.getenv(key)
    try:
        return float(value) if value is not None else default
    except ValueError:
        print(f"警告: 环境变量 {key} 的值 '{value}' 无法转换为浮点数，使用默认值 {default}")
        return default

def get_env_str(key, default):
    """获取字符串环境变量"""
    return os.getenv(key, default)

def get_env_int(key, default):
    """获取整数型环境变量"""
    value = os.getenv(key)
    try:
        return int(value) if value is not None else default
    except ValueError:
        print(f"警告: 环境变量 {key} 的值 '{value}' 无法转换为整数，使用默认值 {default}")
        return default

# 加载环境变量
load_env_file()

# 配置
INPUT_DIR = get_env_str('WATERMARK_INPUT_DIR', 'input')  # 输入文件夹
OUTPUT_DIR = get_env_str('WATERMARK_OUTPUT_DIR', 'output')  # 输出文件夹
FONT_PATH = get_env_str('WATERMARK_TIME_FONT_PATH', 'fonts/TickingTimebombBB.ttf')  # 时间戳字体路径
LOCATION_FONT_PATH = get_env_str('WATERMARK_LOCATION_FONT_PATH', 'fonts/unifont-16.0.04.otf')  # 地理位置字体路径
FONT_SIZE_RATIO = get_env_float('WATERMARK_TIME_FONT_SIZE_RATIO', 0.04)  # 字体高度占图片最短边的比例
LOCATION_FONT_SIZE_RATIO = get_env_float('WATERMARK_LOCATION_FONT_SIZE_RATIO', 0.03)  # 地理位置字体高度占图片最短边的比例
MARGIN_RATIO = get_env_float('WATERMARK_MARGIN_RATIO', 0.02)  # 外边距占图片宽高的比例
PADDING_RATIO = get_env_float('WATERMARK_PADDING_RATIO', 0.01)  # 内边距占图片宽高的比例
BLUR_RADIUS = get_env_int('WATERMARK_BLUR_RADIUS', 10)  # 高斯模糊半径
LINE_SPACING = get_env_float('WATERMARK_LINE_SPACING', 1.5)  # 行间距倍数
AMAP_API_KEY = get_env_str('WATERMARK_AMAP_API_KEY', 'xxx')  # 高德地图API密钥

# 支持的图片格式
IMAGE_EXTS = get_env_str('WATERMARK_IMAGE_EXTS', '.jpg,.jpeg,.png').split(',')

# 默认压缩参数
DEFAULT_JPEG_QUALITY = get_env_int('WATERMARK_DEFAULT_JPEG_QUALITY', 95)
DEFAULT_JPEG_SUBSAMPLING = get_env_int('WATERMARK_DEFAULT_JPEG_SUBSAMPLING', 0)

def convert_to_degrees(value):
    """Convert GPS coordinates from EXIF format to degrees"""
    d = float(value[0][0]) / float(value[0][1])
    m = float(value[1][0]) / float(value[1][1])
    s = float(value[2][0]) / float(value[2][1])
    return d + (m / 60.0) + (s / 3600.0)

def get_location_string(exif_dict):
    """从EXIF中获取GPS信息并格式化"""
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

        lat = convert_to_degrees(lat_data)
        lon = convert_to_degrees(lon_data)
        
        # 经度在前纬度在后，逗号分割
        location_str = f"{lon},{lat}"
        print(f"location_str: {location_str}")
        
        if lat_ref == b'S':
            lat = -lat
        if lon_ref == b'W':
            lon = -lon
            
        formatted_location = f"{abs(lat):.6f}{'S' if lat < 0 else 'N'} {abs(lon):.6f}{'W' if lon < 0 else 'E'}"
        
        regeo_result = regeo_from_amap(location_str)
        
        if regeo_result['status'] == '1':
            # 获取省市区信息
            address_component = regeo_result.get('regeocode', {}).get('addressComponent', {})
            province = address_component.get('province', '')
            city = address_component.get('city', '')
            district = address_component.get('district', '')
            
            # 如果city是列表（为空的情况），转换为空字符串
            if isinstance(city, list):
                city = ''
            
            # 组合省市区，去除空值
            location_parts = [part for part in [province, city, district] if part]
            return ''.join(location_parts) if location_parts else formatted_location
        else:
            return formatted_location

    except Exception:
        return None
      
def regeo_from_amap(location_str):
    """高德地图通过经纬度获取位置信息"""
    url = f"https://restapi.amap.com/v3/geocode/regeo?key={AMAP_API_KEY}&location={location_str}"
    response = requests.get(url)
    return response.json()

def get_exif_info(img_path):
    """获取EXIF中的时间和位置信息"""
    try:
        exif_dict = piexif.load(img_path)
        # 获取时间
        dt_bytes = exif_dict['Exif'].get(piexif.ExifIFD.DateTimeOriginal)
        if dt_bytes:
            dt_str = dt_bytes.decode('utf-8')
            # EXIF 格式: 'YYYY:MM:DD HH:MM:SS'
            dt = datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S').strftime('%Y-%m-%d  %H:%M:%S')
        else:
            dt = None
        
        # 获取位置
        location = get_location_string(exif_dict)
        
        print(f"location: {location}")
        
        return dt, location
    except Exception:
        return None, None

def get_jpeg_quality(img_path):
    """获取JPEG图片的压缩质量和色度采样参数"""
    try:
        with Image.open(img_path) as img:
            if not hasattr(img, 'quantization'):
                return None, None
            
            # 获取量化表
            qtables = img.quantization
            if not qtables:
                return None, None
            
            # 估算质量
            if len(qtables) >= 2:
                # 有色度量化表，说明是4:2:0或4:2:2采样
                subsampling = 2  # 4:2:0
            else:
                # 只有亮度量化表，说明是4:4:4采样
                subsampling = 0  # 4:4:4
            
            # 根据量化表估算质量
            qsum = sum(sum(t) for t in qtables.values())
            qlen = sum(len(t) for t in qtables.values())
            quality = int(100 - (qsum / qlen) / 2)
            quality = max(1, min(100, quality))  # 确保在1-100范围内
            
            return quality, subsampling
    except Exception as e:
        print(f"无法读取压缩参数: {e}")
        return None, None

def get_average_brightness(img, bbox):
    """获取指定区域的平均亮度"""
    region = img.crop(bbox)
    # 转换为灰度图
    if region.mode != 'L':
        region = region.convert('L')
    # 计算平均亮度
    return np.array(region).mean()

def add_watermark(img, text_lines, font_path, location_font_path):
    width, height = img.size
    # 使用最短边作为字体大小的基准
    base_size = min(width, height)
    
    # 创建两种字体
    time_font = ImageFont.truetype(font_path, int(base_size * FONT_SIZE_RATIO))
    location_font = ImageFont.truetype(location_font_path, int(base_size * LOCATION_FONT_SIZE_RATIO))
    
    # 计算所有文本行的最大宽度和总高度
    draw = ImageDraw.Draw(img)
    max_text_w = 0
    total_text_h = 0
    line_heights = []
    
    # 分别计算每行文本的尺寸（使用不同的字体）
    for i, text in enumerate(text_lines):
        if not text:
            continue
        # 第一行使用时间字体，第二行使用位置字体
        font = time_font if i == 0 else location_font
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_w = right - left
        text_h = bottom - top
        max_text_w = max(max_text_w, text_w)
        line_heights.append(text_h)
        total_text_h += text_h
    
    # 添加行间距
    if len(line_heights) > 1:
        total_text_h = int(total_text_h + (len(line_heights) - 1) * (base_size * FONT_SIZE_RATIO * (LINE_SPACING - 1)))
    
    # 计算边距和内边距（也基于最短边）
    margin_x = int(base_size * MARGIN_RATIO)
    margin_y = int(base_size * MARGIN_RATIO)
    padding = int(base_size * PADDING_RATIO)
    
    # 计算文本框位置（包含内边距）
    x = int(width - max_text_w - margin_x - padding * 2)
    y = int(height - total_text_h - margin_y - padding * 2)
    
    # 定义文本框区域，扩大模糊区域以实现柔和边缘
    blur_padding = padding * 2
    box_x0 = int(x - blur_padding)
    box_y0 = int(y - blur_padding)
    box_x1 = int(x + max_text_w + padding * 2 + blur_padding)
    box_y1 = int(y + total_text_h + padding * 2 + blur_padding)
    text_box = (box_x0, box_y0, box_x1, box_y1)
    
    # 提取背景区域并模糊
    background = img.crop(text_box)
    blurred = background.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
    
    # 创建渐变遮罩
    mask = Image.new('L', (box_x1 - box_x0, box_y1 - box_y0), 0)
    mask_draw = ImageDraw.Draw(mask)
    
    # 绘制中心矩形（完全不透明）
    inner_box = (
        blur_padding,
        blur_padding,
        box_x1 - box_x0 - blur_padding,
        box_y1 - box_y0 - blur_padding
    )
    mask_draw.rectangle(inner_box, fill=255)
    
    # 应用高斯模糊到遮罩以创建柔和边缘
    mask = mask.filter(ImageFilter.GaussianBlur(blur_padding / 2))
    
    # 使用遮罩合成模糊背景
    img.paste(blurred, (box_x0, box_y0), mask)
    
    # 计算区域平均亮度并选择文字颜色
    brightness = get_average_brightness(img, (x, y, x + max_text_w + padding * 2, y + total_text_h + padding * 2))
    text_color = (0, 0, 0, 255) if brightness > 128 else (255, 255, 255, 255)
    
    # 绘制文本（使用统一的内边距）
    current_y = y + padding
    for i, text in enumerate(text_lines):
        if not text:
            continue
        # 选择对应的字体
        font = time_font if i == 0 else location_font
        # 计算每行文本的宽度以实现右对齐
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_w = right - left
        text_x = int(x + padding + (max_text_w - text_w))  # 右对齐
        
        draw.text((text_x, current_y), text, font=font, fill=text_color)
        if i < len(text_lines) - 1:  # 不是最后一行
            current_y = int(current_y + line_heights[i] + (base_size * FONT_SIZE_RATIO * (LINE_SPACING - 1)))
    
    return img

def process_images(input_dir, output_dir, font_path, location_font_path):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    for fname in os.listdir(input_dir):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in IMAGE_EXTS:
            continue
        in_path = os.path.join(input_dir, fname)
        out_path = os.path.join(output_dir, fname)
        try:
            # 读取原始EXIF信息
            exif_dict = piexif.load(in_path)
            
            img = Image.open(in_path).convert('RGBA')
            dt, location = get_exif_info(in_path)
            if not dt:
                print(f"未找到时间: {fname}")
                continue
            
            # 准备文本行
            text_lines = [dt]
            if location:
                text_lines.append(location)
            
            img = add_watermark(img, text_lines, font_path, location_font_path)
            # 保持原格式和高质量
            if ext in ['.jpg', '.jpeg']:
                quality, subsampling = get_jpeg_quality(in_path)
                img = img.convert('RGB')
                # 如果无法获取原始参数，使用默认的高质量设置
                if quality is None:
                    quality = DEFAULT_JPEG_QUALITY
                if subsampling is None:
                    subsampling = DEFAULT_JPEG_SUBSAMPLING
                print(f"使用压缩参数 - 质量: {quality}, 色度采样: {subsampling} - {fname}")
                
                # 转换EXIF为bytes
                exif_bytes = piexif.dump(exif_dict)
                
                # 保存图片时包含EXIF信息
                img.save(out_path, 'JPEG', quality=quality, subsampling=subsampling, exif=exif_bytes)
            else:
                # PNG不支持EXIF，但我们仍然保存图片
                img.save(out_path, 'PNG')
            print(f"处理完成: {fname}")
        except Exception as e:
            print(f"处理失败: {fname}, 错误: {e}")

if __name__ == '__main__':
    process_images(INPUT_DIR, OUTPUT_DIR, FONT_PATH, LOCATION_FONT_PATH)
