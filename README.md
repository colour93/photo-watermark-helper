# Photo Watermark Helper

一个功能强大的照片水印工具，支持命令行和服务器模式，可添加时间戳和地理位置水印。

## 功能特点

- 多种运行模式：
  - 命令行批处理模式
  - 交互式TUI界面模式
  - Web服务器API模式（支持REST和WebSocket）
- 多种输入格式支持：
  - 本地文件处理
  - Base64编码图片处理
  - WebSocket流式处理
- 智能图片水印：
  - 读取照片EXIF信息中的拍摄时间
  - 读取GPS信息并通过高德地图API转换为地理位置
  - 智能文字颜色（根据背景自动选择黑/白）
  - 美观的模糊背景效果
- 高质量处理：
  - 保留原始EXIF信息
  - 保持原图质量和压缩参数
  - 异步高性能处理，支持批量操作
- 完全可配置：
  - 支持环境变量或.env文件配置
  - 可自定义字体、大小、位置和效果

## 安装

### 使用PDM安装（推荐）

```bash
# 克隆仓库
git clone https://github.com/colour93/photo-watermark-helper.git
cd photo-watermark-helper

# 使用PDM安装依赖
pdm install
```

### 使用 Pip 安装

```bash
# 克隆仓库
git clone https://github.com/colour93/photo-watermark-helper.git
cd photo-watermark-helper

# 安装依赖
pip install -r requirements.txt
```

### 使用 pdm 安装

```bash
# 克隆仓库
git clone https://github.com/colour93/photo-watermark-helper.git
cd photo-watermark-helper

# 安装依赖
pdm install
```

## 配置

支持通过环境变量或 `.env` 文件配置所有参数。

1. 复制 `.env.example` 为 `.env` 或 `.env.local`：

```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，根据需要修改配置：

```env
# 基本路径配置
WATERMARK_INPUT_DIR=input
WATERMARK_OUTPUT_DIR=output

# 字体配置
WATERMARK_TIME_FONT_PATH=sarasa-mono-sc-semibold.ttf
WATERMARK_LOCATION_FONT_PATH=sarasa-mono-sc-semibold.ttf

# 字体大小配置（占图片最短边的比例）
WATERMARK_TIME_FONT_SIZE_RATIO=0.04
WATERMARK_LOCATION_FONT_SIZE_RATIO=0.03

# 布局配置
WATERMARK_MARGIN_RATIO=0.02
WATERMARK_PADDING_RATIO=0.01
WATERMARK_LINE_SPACING=1.5

# 效果配置
WATERMARK_BLUR_RADIUS=10

# 图片格式配置
WATERMARK_IMAGE_EXTS=.jpg,.jpeg,.png
WATERMARK_DEFAULT_JPEG_QUALITY=95
WATERMARK_DEFAULT_JPEG_SUBSAMPLING=0

# API配置
WATERMARK_AMAP_API_KEY=你的高德地图API密钥

# 服务器配置
WATERMARK_SERVER_HOST=127.0.0.1
WATERMARK_SERVER_PORT=9393
API_TOKEN=your_secret_api_token_here
DEBUG=false

# 日志配置
WATERMARK_LOG_LEVEL=INFO
WATERMARK_LOG_FILE=logs/watermarker.log
```

## 使用方法

### 命令行批处理模式

```bash
# 使用默认配置处理图片
python -m watermarker batch

# 指定输入输出目录
python -m watermarker batch --input ./my_photos --output ./watermarked_photos

# 不使用TUI界面（适用于脚本中调用）
python -m watermarker batch --no-tui
```

### 交互式TUI界面模式

```bash
python -m watermarker interactive
```

### 服务器模式

```bash
# 使用默认配置启动服务器
python -m watermarker server

# 指定主机和端口
python -m watermarker server --host 127.0.0.1 --port 5000
```

## API接口说明

当以服务器模式运行时，可以通过以下API接口处理图片：

### REST API

- `GET /` - 服务器状态检查
- `POST /watermark/file` - 处理上传的图片文件

#### API使用示例

##### 文件上传处理
```bash
curl -X POST "http://localhost:9393/watermark/file" \
  -H "X-API-Key: your_secret_api_token_here" \
  -F "file=@examples/input/C93_0011.jpg" \
  --output watermarked_output.jpg
```

### WebSocket API

- `WebSocket /watermark/stream` - 实时流式文件处理

#### WebSocket接口详解


### 大文件分块上传说明

由于 WebSocket 消息有大小限制（通常为 1MB），客户端会自动将大文件分块上传。无需手动操作，客户端会自动处理分块和重组，服务器也已支持分块接收。

**注意事项：**
- 单张图片超过 1MB 时会自动分块上传。
- 分块上传无需用户干预，进度会在客户端界面显示。
- 如果遇到 `message too big` 错误，请确保使用新版客户端和服务器。

##### 连接建立

1. 客户端建立WebSocket连接
   ```javascript
   const socket = new WebSocket('ws://localhost:9393/watermark/stream');
   ```

2. 连接成功后，首先发送文件信息（JSON格式）：
   ```json
   {
     "token": "your_secret_api_token_here",  // 如果配置了API_TOKEN则必需
     "filename": "image.jpg",                // 文件名
     "size": 1024000,                       // 文件大小（字节）
     "chunks": 3,                           // 分块数量（可选，大文件时使用）
     "chunk_size": 1048576                  // 分块大小（可选，默认1MB）
   }
   ```

3. 然后发送文件的二进制数据（支持分块发送）：
   ```javascript
   // 小文件（< 1MB）直接发送
   if (file.size <= 1048576) {
     socket.send(fileData);
   } else {
     // 大文件分块发送
     const chunkSize = 1048576 - 1024; // 1MB - 1KB buffer
     const totalChunks = Math.ceil(file.size / chunkSize);
     
     for (let i = 0; i < totalChunks; i++) {
       const start = i * chunkSize;
       const end = Math.min(start + chunkSize, file.size);
       const chunk = fileData.slice(start, end);
       
       socket.send(chunk);
       
       // 等待服务器确认（除最后一块外）
       if (i < totalChunks - 1) {
         await waitForChunkAck();
       }
     }
   }
   ```

4. 服务器处理文件并返回JSON响应：
   ```json
   {
     "success": true,
     "message": "Image successfully watermarked",
     "timestamp": "2025-07-23T10:15:30.123456",
     "output_size": 1234567,
     "output_filename": "watermarked_image.jpg"
   }
   ```

5. 如果处理成功，服务器随后发送处理后的文件二进制数据

6. 如果处理失败，服务器返回错误响应：
   ```json
   {
     "success": false,
     "message": "Error processing file: Invalid image format"
   }
   ```

##### Python WebSocket示例

项目中包含了一个完整的Python WebSocket客户端示例（`examples/websocket_file_client.py`）：

```bash
# 使用WebSocket文件流客户端
python examples/websocket_file_client.py

# 或处理特定文件
python examples/websocket_file_client.py /path/to/image.jpg
```

##### JavaScript WebSocket分块上传示例

```javascript
async function uploadImageViaWebSocket(file, apiToken) {
  const socket = new WebSocket('ws://localhost:9393/watermark/stream');
  const CHUNK_SIZE = 1024 * 1024 - 1024; // 1MB - 1KB buffer
  
  return new Promise((resolve, reject) => {
    socket.onopen = async () => {
      try {
        // 1. 发送文件信息
        const totalChunks = file.size > CHUNK_SIZE ? 
          Math.ceil(file.size / CHUNK_SIZE) : 1;
        
        const fileInfo = {
          token: apiToken,
          filename: file.name,
          size: file.size,
          chunks: totalChunks,
          chunk_size: CHUNK_SIZE
        };
        
        socket.send(JSON.stringify(fileInfo));
        
        // 2. 读取文件数据
        const fileData = await file.arrayBuffer();
        
        // 3. 发送文件数据（分块或整体）
        if (file.size <= CHUNK_SIZE) {
          // 小文件，直接发送
          socket.send(fileData);
        } else {
          // 大文件，分块发送
          let chunkIndex = 0;
          
          const sendNextChunk = () => {
            if (chunkIndex < totalChunks) {
              const start = chunkIndex * CHUNK_SIZE;
              const end = Math.min(start + CHUNK_SIZE, file.size);
              const chunk = fileData.slice(start, end);
              
              socket.send(chunk);
              chunkIndex++;
            }
          };
          
          // 开始发送第一块
          sendNextChunk();
          
          // 监听服务器的块确认消息
          socket.addEventListener('message', (event) => {
            try {
              const response = JSON.parse(event.data);
              
              // 如果是块确认消息，继续发送下一块
              if (response.chunk_received && chunkIndex < totalChunks) {
                sendNextChunk();
              }
            } catch (e) {
              // 忽略非JSON消息（可能是最终的文件数据）
            }
          });
        }
      } catch (error) {
        reject(error);
      }
    };
    
    let awaitingResult = false;
    socket.onmessage = (event) => {
      try {
        // 尝试解析JSON响应
        const response = JSON.parse(event.data);
        
        // 如果是块确认消息，已在上面处理
        if (response.chunk_received) {
          return;
        }
        
        // 如果是处理结果
        if (response.success !== undefined) {
          if (response.success) {
            awaitingResult = true;
            console.log('图片处理成功，等待文件数据...');
          } else {
            reject(new Error(response.message || '处理失败'));
          }
        }
      } catch (e) {
        // 如果不是JSON，可能是文件二进制数据
        if (awaitingResult && event.data instanceof ArrayBuffer) {
          const blob = new Blob([event.data]);
          resolve(blob);
        }
      }
    };
    
    socket.onerror = (error) => reject(error);
    socket.onclose = () => {
      if (!awaitingResult) {
        reject(new Error('连接意外关闭'));
      }
    };
  });
}

// 使用示例
const fileInput = document.getElementById('file-input');
fileInput.addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (file) {
    try {
      const processedBlob = await uploadImageViaWebSocket(file, 'your_api_token');
      
      // 下载处理后的文件
      const url = URL.createObjectURL(processedBlob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `watermarked_${file.name}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('上传失败:', error);
    }
  }
});
```

##### WebSocket优势

1. **高效传输**: 直接传输文件二进制数据，无需Base64编码/解码
2. **低延迟**: 避免HTTP连接建立的开销，特别适合批量处理
3. **持久连接**: 无需反复建立连接，提高性能
4. **实时反馈**: 即时获取处理结果，适合交互式应用
5. **双向通信**: 客户端和服务器可以随时交换信息
6. **状态保持**: 连接期间可以维护会话状态
7. **分块上传**: 自动处理大文件分块，突破消息大小限制
8. **容错性**: 分块确认机制确保数据完整性

注意：WebSocket现在处理原始文件数据，支持更大的文件和更好的性能。分块上传功能让您可以处理任意大小的图片文件。

## 开发说明

 项目结构：

```
watermarker/
├── __init__.py       # 包初始化
├── main.py           # 主入口
├── core/             # 核心功能模块
│   ├── __init__.py
│   └── processor.py  # 水印处理器
├── cli/              # 命令行界面
│   ├── __init__.py
│   └── commands.py   # 命令定义
├── server/           # 服务器模块
│   ├── __init__.py
│   └── app.py        # FastAPI应用
└── utils/            # 工具函数
    ├── __init__.py
    ├── config.py     # 配置管理
    ├── file_utils.py # 文件工具
    └── logger.py     # 日志工具
```

## 配置参数详解

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
- `WATERMARK_AMAP_API_KEY`: 高德地图 API 密钥（用于地理位置转换）

### 服务器配置
- `WATERMARK_SERVER_HOST`: 服务器监听地址（默认: 127.0.0.1）
- `WATERMARK_SERVER_PORT`: 服务器端口（默认: 9393）
- `API_TOKEN`: API访问令牌（用于保护API访问安全，不设置则无需认证）
- `DEBUG`: 是否启用调试模式（默认: false）

### 日志配置
- `WATERMARK_LOG_LEVEL`: 日志级别（默认: INFO）
- `WATERMARK_LOG_FILE`: 日志文件路径（默认: logs/watermarker.log）

## 注意事项

1. 确保字体文件存在且有正确的权限
2. 高德地图 API 密钥需要自行申请 [高德地图开放平台控制台](https://console.amap.com/dev/key/app)
3. PNG 格式不支持保存 EXIF 信息
4. 建议使用 Python 3.12

## 示例效果

| 原图 | 水印后 |
|:---:|:---:|
| ![原图1](docs/input/C93_0011.jpg) | ![水印1](docs/output/C93_0011.jpg) |
| ![原图2](docs/input/C93_1088.jpg) | ![水印2](docs/output/C93_1088.jpg) |
| ![原图3](docs/input/C93_2155.jpg) | ![水印3](docs/output/C93_2155.jpg) |

## 许可证

MIT License

