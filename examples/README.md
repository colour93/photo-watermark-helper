# 示例文件

示例照片由 Git LFS 管理，不会进入 Python wheel 或 sdist：

```bash
git lfs install
git lfs pull
```

## CLI 示例

```bash
uv run watermarker inspect input/C93_0011.jpg
uv run watermarker preview input/C93_0011.jpg --style glass
uv run watermarker batch input/ -o output/ --on-exists overwrite
```

## WebSocket 客户端

先安装可选服务端依赖并启动服务：

```bash
uv sync --extra server
uv run watermarker server
```

再运行客户端：

```bash
uv run python examples/websocket_file_client.py
uv run python examples/websocket_file_client.py /path/to/photo.jpg
```

默认地址为 `ws://localhost:9393/watermark/stream`。启用 `WATERMARK_API_TOKEN` 时，请同步更新客户端令牌。
