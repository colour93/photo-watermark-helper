# Photo Watermark Helper

面向照片批处理的安全水印 CLI：从 EXIF 提取拍摄时间、GPS、相机和镜头信息，支持预览、样式预设、智能位置及 REST/WebSocket 服务。

## 安装

项目使用 [uv](https://docs.astral.sh/uv/) 管理 Python 与依赖：

```bash
uv sync
uv run watermarker --help
```

如需服务端：

```bash
uv sync --extra server
```

也可以安装为命令：

```bash
uv tool install .
watermarker --help
```

## 推荐旅程

```bash
# 1. 检查可提取的水印信息
uv run watermarker inspect photo.jpg

# 2. 快速生成低分辨率预览
uv run watermarker preview photo.jpg --style glass --open

# 3. 处理单张或多张图片
uv run watermarker add photo.jpg another.jpg -o output/

# 4. 安全批处理；默认跳过已存在文件
uv run watermarker batch photos/ -o output/ --recursive
```

直接运行 `uv run watermarker` 会进入首次使用向导。

## 常用功能

### 样式与内容

内置四种样式：

- `minimal`：低干扰的现代信息水印，默认样式。
- `glass`：模糊与半透明底板，适合复杂背景。
- `film`：较强的信息条视觉。
- `stamp`：描边时间戳风格。

```bash
uv run watermarker preview photo.jpg \
  --style minimal \
  --position auto \
  --fields time,location,camera,lens \
  --date-format "%Y.%m.%d %H:%M" \
  --opacity 0.85 \
  --scale 1.1
```

位置支持 `auto`、`top-left`、`top-right`、`bottom-left`、`bottom-right`。`auto` 会比较四角的纹理和边缘密度，选择干扰较少的位置。

### 时间与地点

时间按以下顺序降级：

```text
DateTimeOriginal → DateTimeDigitized → DateTime → 文件修改时间
```

地点优先使用高德逆地理编码；未配置 API、请求失败或使用 `--no-geocode` 时显示 GPS 坐标。也可以手动覆盖：

```bash
uv run watermarker add photo.jpg --time "2026-07-14 18:30" --location "上海"
```

### 批处理安全性

```bash
# 仅查看将要执行的操作
uv run watermarker batch photos/ -o output/ --dry-run

# 冲突策略：skip（默认）、rename、overwrite
uv run watermarker batch photos/ -o output/ --on-exists rename

# 控制并发数
uv run watermarker batch photos/ -o output/ --workers 8
```

默认文件名会增加 `_watermarked`，输出通过临时文件原子写入。输入输出不能是同一文件。全部成功时退出码为 `0`，出现处理失败时为 `1`，命令或配置错误时为 `2`。

### 自动化输出

```bash
uv run watermarker --json inspect photo.jpg
uv run watermarker --json batch photos/ -o output/
uv run watermarker --quiet batch photos/ -o output/
uv run watermarker --no-color batch photos/ -o output/
```

### 配置检查

```bash
uv run watermarker doctor
uv run watermarker config show
uv run watermarker config init
```

配置优先读取 `WATERMARK_CONFIG` 指定的文件，否则依次读取当前目录的 `.env.local`、`.env`。完整变量见 [.env.example](.env.example)。CLI 参数优先于环境默认值。

## 图像与元数据

- 支持 JPEG、PNG、WebP，可通过配置扩展后缀。
- 自动应用 EXIF orientation，避免手机竖图方向错误。
- 保留 EXIF、ICC profile 和 DPI；应用方向后会移除 orientation 标签。
- JPEG 默认复用原始量化表和采样方式；指定 `--quality` 时使用明确的重新编码质量。
- 长文本会自动缩小以适配画面安全区。

## 服务端

```bash
uv sync --extra server
uv run watermarker server --host 127.0.0.1 --port 9393
```

- `POST /watermark/file`：上传并返回处理后的图片。
- `WebSocket /watermark/stream`：支持分块上传。
- 设置 `WATERMARK_API_TOKEN` 后，通过 `X-API-Key` 或 WebSocket 文件信息中的 `token` 鉴权。

客户端示例见 [examples/websocket_file_client.py](examples/websocket_file_client.py)。

## 示例图片与仓库体积

`examples/**/*.{jpg,jpeg,png,webp}` 由 Git LFS 管理，并且被明确排除在 wheel 和 sdist 之外。克隆后需要示例原图时运行：

```bash
git lfs install
git lfs pull
```

普通 CLI 安装不会包含示例图片，也不会安装服务端依赖。
