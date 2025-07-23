# Photo Watermark

一个用于给照片添加时间戳和地理位置水印的 Python 工具。

## 功能特点

- 读取照片 EXIF 信息中的拍摄时间
- 读取 GPS 信息并通过高德地图 API 转换为地理位置
- 支持自定义字体和样式
- 智能文字颜色（根据背景自动选择黑/白）
- 美观的模糊背景效果
- 保留原始 EXIF 信息
- 保持原图质量
- 完全可配置的参数

## 安装

1. 克隆仓库：
```bash
git clone <repository_url>
cd photo-watermark
```

2. 安装依赖：
```bash
pip install pillow piexif requests python-dotenv numpy
```

3. 准备字体文件：
   - 将时间戳字体文件放在 `fonts/TickingTimebombBB.ttf`
   - 将地理位置字体文件（支持中文）放在 `fonts/unifont-16.0.04.otf`

4. 配置环境变量：
   - 复制 `.env.example` 为 `.env`
   - 根据需要修改配置

## 使用方法

1. 将需要处理的照片放入 input 文件夹（可配置）

2. 运行脚本：
```bash
python watermark.py
```

3. 处理后的照片将保存在 output 文件夹（可配置）

## 配置说明

支持通过环境变量或 .env 文件配置所有参数：

### 目录配置
- `WATERMARK_INPUT_DIR`: 输入文件夹路径（默认: input）
- `WATERMARK_OUTPUT_DIR`: 输出文件夹路径（默认: output）

### 字体配置
- `WATERMARK_TIME_FONT_PATH`: 时间戳字体路径
- `WATERMARK_LOCATION_FONT_PATH`: 地理位置字体路径
- `WATERMARK_TIME_FONT_SIZE_RATIO`: 时间戳字体大小比例（相对于图片最短边）
- `WATERMARK_LOCATION_FONT_SIZE_RATIO`: 地理位置字体大小比例

### 布局配置
- `WATERMARK_MARGIN_RATIO`: 外边距比例
- `WATERMARK_PADDING_RATIO`: 内边距比例
- `WATERMARK_LINE_SPACING`: 行间距倍数
- `WATERMARK_BLUR_RADIUS`: 背景模糊半径

### 图片处理
- `WATERMARK_IMAGE_EXTS`: 支持的图片格式（逗号分隔）
- `WATERMARK_DEFAULT_JPEG_QUALITY`: 默认 JPEG 质量（1-100）
- `WATERMARK_DEFAULT_JPEG_SUBSAMPLING`: JPEG 色度采样（0=4:4:4, 2=4:2:0）

### API 配置
- `WATERMARK_AMAP_API_KEY`: 高德地图 API 密钥

## 环境变量优先级

1. `.env.local`（如果存在）
2. `.env`
3. 默认值

建议将特定环境的配置放在 `.env.local` 中（已加入 .gitignore）

## 注意事项

1. 确保字体文件存在且有正确的权限
2. 高德地图 API 密钥需要自行申请 [https://console.amap.com/dev/key/app](高德地图开放平台控制台)
3. PNG 格式不支持保存 EXIF 信息
4. 建议使用 Python 3.12

## 示例效果

处理前：
```
input/
  ├── photo1.jpg
  └── photo2.jpg
```

处理后：
```
output/
  ├── photo1.jpg  # 右下角添加时间戳和地理位置
  └── photo2.jpg  # 保持原始质量和 EXIF 信息
```
