# WebSocket 客户端示例

这个目录包含了 Photo Watermark Helper 的使用示例。

## WebSocket 客户端 (websocket_client.py)

这是一个展示如何使用 Python 通过 WebSocket 连接到 Photo Watermark Helper 服务的示例。

### 准备工作

1. 确保已安装所需的依赖：
   ```bash
   pip install websockets pillow
   ```

2. 确保已启动 Photo Watermark Helper 的服务器：
   ```bash
   python -m watermarker server
   ```

3. 如果您设置了 API 令牌，请在 `websocket_client.py` 中更新 `API_TOKEN` 变量。

### 使用方法

1. 处理目录中的所有图片：
   ```bash
   python websocket_client.py
   ```
   这将处理 `examples/input` 目录中的所有图片，并将结果保存到 `examples/output` 目录中。

2. 处理单个图片：
   ```bash
   python websocket_client.py /path/to/your/image.jpg
   ```
   
### 功能特点

- 支持批量处理图片
- 支持 JPEG 和 PNG 格式
- 自动保存处理后的图片
- 显示处理后图片的信息

### 代码结构

- `process_image(image_path)`: 处理单张图片
- `process_batch(input_dir)`: 批量处理目录中的图片
- `main()`: 主函数，处理命令行参数

### 注意事项

- 服务器地址默认为 `ws://localhost:9393/watermark/stream`，如需修改请更新代码中的 `SERVER_URL` 变量
- 如果遇到连接问题，请确保服务器已正确启动且端口号配置正确
