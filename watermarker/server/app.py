"""FastAPI server for the watermarking service."""

import os
import io
from typing import Optional
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
import uvicorn
from loguru import logger

from ..core.processor import WatermarkProcessor
from ..utils.config import config
from ..utils.file_utils import get_temp_filepath


# Models for API responses
class FileProcessResponse(BaseModel):
    """Response model for file processing."""
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Status message")
    timestamp: str = Field(..., description="Processing timestamp")
    file_path: Optional[str] = Field(None, description="Path to the processed file")


# Setup API key security
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(api_key: str = Depends(api_key_header)):
    """Validate API key if configured."""
    if not config.API_TOKEN:  # No API key required
        return True
    
    if api_key != config.API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


class WatermarkServer:
    """FastAPI server for watermarking service."""
    
    def __init__(self):
        """Initialize server."""
        self.app = FastAPI(
            title="Photo Watermark API",
            description="API for adding watermarks to photos",
            version="0.1.0",
        )
        
        # Setup CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Initialize processor
        self.processor = WatermarkProcessor()
        
        # Register routes
        self.register_routes()
    
    def register_routes(self):
        """Register API routes."""
        
        @self.app.get("/", tags=["Info"])
        async def root():
            """Server status endpoint."""
            return {"status": "online", "service": "Photo Watermark API"}
        
        @self.app.post("/watermark/file", tags=["Watermark"])
        async def watermark_file(
            file: UploadFile = File(...),
            _: bool = Depends(get_api_key)
        ):
            """Watermark an uploaded image file."""
            try:
                logger.info(f"处理文件上传请求: {file.filename}")
                
                # Create temp files for input and output
                suffix = Path(file.filename).suffix if file.filename else ".jpg"
                input_temp = get_temp_filepath(suffix=suffix)
                output_temp = get_temp_filepath(suffix=suffix)
                
                logger.debug(f"创建临时文件: 输入={input_temp}, 输出={output_temp}")
                
                # Save uploaded file to temp
                with open(input_temp, "wb") as temp_file:
                    contents = await file.read()
                    temp_file.write(contents)
                
                logger.info(f"上传文件已保存: {input_temp}, 大小: {len(contents)} bytes")
                
                # Process image
                logger.info(f"开始处理图像: {input_temp}")
                success = await self.processor.process_single_image_async(
                    input_path=input_temp, 
                    output_path=output_temp,
                    font_path=None,
                    location_font_path=None
                )
                
                if not success:
                    logger.error(f"图像处理失败: {input_temp}")
                    return JSONResponse(
                        status_code=500,
                        content={
                            "success": False, 
                            "message": "Failed to process image",
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                
                logger.info(f"图像处理成功: {output_temp}")
                
                # Return file
                return FileResponse(
                    output_temp,
                    media_type=f"image/{suffix[1:]}",
                    filename=f"watermarked_{file.filename}"
                )
                
            except Exception as e:
                logger.error(f"处理文件时发生错误: {str(e)}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "success": False, 
                        "message": f"Error processing image: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }
                )
        
        @self.app.websocket("/watermark/stream")
        async def watermark_stream(websocket: WebSocket):
            """WebSocket endpoint for streaming file processing."""
            await websocket.accept()
            logger.info("WebSocket连接已建立")
            
            try:
                while True:
                    # Receive binary data
                    try:
                        # 首先接收文件信息
                        file_info = await websocket.receive_json()
                        logger.info(f"WebSocket: 接收到文件信息: {file_info}")
                        
                        # Check for token if required
                        if config.API_TOKEN:
                            token = file_info.get("token")
                            if token != config.API_TOKEN:
                                await websocket.send_json({
                                    "success": False,
                                    "message": "Invalid API token"
                                })
                                continue
                        
                        # 获取文件名和大小
                        filename = file_info.get("filename", "image.jpg")
                        file_size = file_info.get("size", 0)
                        chunks = file_info.get("chunks", 1)
                        
                        if file_size <= 0:
                            await websocket.send_json({
                                "success": False,
                                "message": "Invalid file size"
                            })
                            continue
                        
                        logger.info(f"WebSocket: 准备接收文件: {filename}, 大小: {file_size} bytes, 分块数: {chunks}")
                        
                        # 接收文件数据 - 支持分块接收
                        file_data = bytearray()
                        
                        if chunks == 1:
                            # 小文件，一次接收
                            data = await websocket.receive_bytes()
                            file_data.extend(data)
                            logger.info(f"WebSocket: 接收到文件数据: {len(data)} bytes")
                        else:
                            # 大文件，分块接收
                            for i in range(chunks):
                                logger.info(f"WebSocket: 等待接收块 {i+1}/{chunks}")
                                chunk_data = await websocket.receive_bytes()
                                file_data.extend(chunk_data)
                                
                                # 发送确认（除了最后一块）
                                if i < chunks - 1:
                                    await websocket.send_json({
                                        "chunk_received": True,
                                        "chunk_number": i + 1,
                                        "total_received": len(file_data)
                                    })
                                
                                logger.info(f"WebSocket: 接收到块 {i+1}/{chunks}: {len(chunk_data)} bytes, 总计: {len(file_data)} bytes")
                        
                        # 验证接收到的数据大小
                        if len(file_data) != file_size:
                            await websocket.send_json({
                                "success": False,
                                "message": f"Data size mismatch: expected {file_size}, got {len(file_data)}"
                            })
                            continue
                        
                        logger.info(f"WebSocket: 文件接收完成，总大小: {len(file_data)} bytes")
                        
                    except Exception as e:
                        logger.error(f"WebSocket: 接收数据错误: {str(e)}")
                        await websocket.send_json({
                            "success": False,
                            "message": f"Error receiving data: {str(e)}"
                        })
                        continue
                    
                    # Process the file
                    try:
                        # Create temp files
                        suffix = Path(filename).suffix if filename else ".jpg"
                        input_temp = get_temp_filepath(suffix=suffix)
                        output_temp = get_temp_filepath(suffix=suffix)
                        
                        logger.info(f"WebSocket: 处理文件，临时路径: {input_temp}")
                        
                        # Save file data to temp
                        with open(input_temp, "wb") as temp_file:
                            temp_file.write(file_data)
                        
                        logger.info(f"WebSocket: 文件已保存: {input_temp}")
                        
                        # Process image
                        success = await self.processor.process_single_image_async(
                            input_path=input_temp, 
                            output_path=output_temp,
                            font_path=None,
                            location_font_path=None
                        )
                        
                        if not success:
                            logger.error(f"WebSocket: 图像处理失败: {input_temp}")
                            await websocket.send_json({
                                "success": False,
                                "message": "Failed to process image"
                            })
                            continue
                        
                        # Read processed file and send back
                        with open(output_temp, "rb") as processed_file:
                            processed_data = processed_file.read()
                        
                        logger.info(f"WebSocket: 图像处理成功，返回数据大小: {len(processed_data)} bytes")
                        
                        # Send success response first
                        await websocket.send_json({
                            "success": True,
                            "message": "Image successfully watermarked",
                            "timestamp": datetime.now().isoformat(),
                            "output_size": len(processed_data),
                            "output_filename": f"watermarked_{filename}"
                        })
                        
                        # Send the processed file data
                        await websocket.send_bytes(processed_data)
                        
                        # Clean up temp files
                        try:
                            os.remove(input_temp)
                            os.remove(output_temp)
                        except Exception:
                            pass
                        
                    except Exception as e:
                        logger.error(f"WebSocket: 处理文件时发生错误: {str(e)}")
                        await websocket.send_json({
                            "success": False,
                            "message": f"Error processing file: {str(e)}"
                        })
                        
            except WebSocketDisconnect:
                logger.info("WebSocket连接已断开")
            
            except Exception as e:
                logger.error(f"WebSocket发生未预期错误: {str(e)}")
                try:
                    await websocket.send_json({
                        "success": False,
                        "message": f"Unexpected error: {str(e)}"
                    })
                except Exception:
                    pass
                
            finally:
                try:
                    await websocket.close()
                except Exception:
                    pass
    
    def run(self, host: str | None = None, port: int | None = None):
        """Run the server."""
        host = host or config.SERVER_HOST
        port = port or config.SERVER_PORT
        
        uvicorn.run(
            self.app, 
            host=host, 
            port=port, 
            log_level="debug" if config.DEBUG else "info"
        )


def create_server() -> WatermarkServer:
    """Create and configure the watermark server."""
    return WatermarkServer()
