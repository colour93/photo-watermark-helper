"""
WebSocket文件流客户端示例 - 用于Photo Watermark Helper
展示如何使用Python通过WebSocket发送文件进行图片处理
使用Rich库构建精美的TUI界面
支持持久连接和批量上传
"""

import asyncio
import json
import os
from pathlib import Path
import sys

import websockets
from PIL import Image
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

# 配置参数
SERVER_URL = "ws://localhost:9393/watermark/stream"
API_TOKEN = "your_secret_api_token_here"  # 使用您在.env中设置的令牌
EXAMPLES_DIR = Path(__file__).parent

# 创建Rich控制台
console = Console()


def print_banner():
    """打印应用程序横幅"""
    banner = """
    [bold cyan]Photo Watermark Helper[/bold cyan] - [green]WebSocket文件流客户端[/green]
    [dim]支持持久连接的水印处理工具[/dim]
    """
    console.print(Panel(banner, border_style="cyan"))


def display_image_info(image_path):
    """显示图片信息"""
    try:
        img = Image.open(image_path)
        file_size = os.path.getsize(image_path)
        
        table = Table(show_header=False, box=None)
        table.add_column("属性", style="cyan")
        table.add_column("值")
        
        table.add_row("文件名", os.path.basename(image_path))
        table.add_row("文件大小", f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB")
        table.add_row("尺寸", f"{img.width} x {img.height} 像素")
        table.add_row("格式", img.format)
        table.add_row("模式", img.mode)
        
        # 尝试获取EXIF信息
        try:
            exif_data = img.getexif() if hasattr(img, "getexif") else None
            if exif_data and 306 in exif_data:  # 306是DateTime标签
                table.add_row("拍摄时间", exif_data[306])
        except Exception:
            pass  # 忽略EXIF读取错误
        
        console.print(Panel(table, title="图片信息", border_style="blue"))
        
    except Exception as e:
        console.print(f"[red]无法读取图片信息: {e}[/red]")


async def process_single_image(websocket, image_path):
    """通过已连接的WebSocket发送单个文件进行处理"""
    # WebSocket消息大小限制 (1MB - 留一些缓冲)
    CHUNK_SIZE = 1024 * 1024 - 1024  # 1MB - 1KB buffer
    
    # 创建进度显示
    with console.status("[bold green]正在处理图片...", spinner="dots") as status:
        try:
            # 读取文件
            status.update("[bold blue]读取图片文件...")
            with open(image_path, "rb") as file:
                file_data = file.read()
            
            file_size = len(file_data)
            filename = os.path.basename(image_path)
            
            console.print(f"[green]文件已读取: {filename}, 大小: {file_size} bytes[/green]")
            
            status.update("[bold cyan]正在发送文件信息...")
            
            # 计算分块数量
            total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE if file_size > CHUNK_SIZE else 1
            
            # 首先发送文件信息
            file_info = {
                "token": API_TOKEN,
                "filename": filename,
                "size": file_size,
                "chunks": total_chunks,
                "chunk_size": CHUNK_SIZE
            }
            
            await websocket.send(json.dumps(file_info))
            
            # 发送文件数据 - 分块发送
            if file_size <= CHUNK_SIZE:
                # 小文件，一次发送
                status.update("[bold magenta]文件较小，一次性发送文件数据...")
                await websocket.send(file_data)
            else:
                # 大文件，分块发送
                status.update(f"[bold magenta]文件较大，开始分块发送 ({total_chunks} 块)...")
                
                for i in range(total_chunks):
                    start = i * CHUNK_SIZE
                    end = min(start + CHUNK_SIZE, file_size)
                    chunk = file_data[start:end]
                    
                    status.update(f"[bold magenta]发送块 {i+1}/{total_chunks} ({len(chunk)} bytes)...")
                    await websocket.send(chunk)
                    
                    # 等待服务器确认（如果不是最后一块）
                    if i < total_chunks - 1:
                        try:
                            ack = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                            ack_data = json.loads(ack)
                            if not ack_data.get("chunk_received"):
                                raise Exception(f"服务器未确认块 {i+1}")
                        except asyncio.TimeoutError:
                            raise Exception(f"等待块 {i+1} 确认超时")
                        except json.JSONDecodeError:
                            raise Exception(f"块 {i+1} 确认响应格式错误")
            
            status.update("[bold orange]文件数据已发送，等待处理结果...")
            
            # 接收处理结果信息
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("success"):
                status.update("[bold green]处理成功，正在接收结果文件...")
                
                # 接收处理后的文件数据
                processed_data = await websocket.recv()
                
                if isinstance(processed_data, bytes):
                    # 确定输出文件名
                    output_dir = EXAMPLES_DIR / "output"
                    output_path = output_dir / filename
                    
                    # 确保输出目录存在
                    os.makedirs(output_dir, exist_ok=True)
                    
                    # 保存处理后的文件
                    with open(output_path, "wb") as out_file:
                        out_file.write(processed_data)
                    
                    # 显示处理结果信息
                    result_table = Table(show_header=False, box=None)
                    result_table.add_column("项目", style="cyan")
                    result_table.add_column("详情")
                    
                    result_table.add_row("状态", "[green]成功[/green]")
                    result_table.add_row("时间戳", response_data.get('timestamp', 'N/A'))
                    result_table.add_row("输出文件", str(output_path))
                    result_table.add_row("输出大小", f"{len(processed_data)} bytes")
                    
                    # 显示输出图片信息
                    try:
                        img = Image.open(output_path)
                        result_table.add_row("图片尺寸", f"{img.width} x {img.height} 像素")
                        result_table.add_row("图片格式", img.format)
                    except Exception:
                        pass
                    
                    console.print(Panel(result_table, title="处理结果", border_style="green"))
                    return True
                else:
                    console.print(Panel("[red]接收到的不是文件数据[/red]", 
                                       title="错误", border_style="red"))
                    return False
            else:
                error_msg = response_data.get('message', '未知错误')
                console.print(Panel(f"[red]处理失败: {error_msg}[/red]", 
                                   title="服务器错误", border_style="red"))
                return False
                
        except Exception as e:
            console.print(Panel(f"[red]发生错误: {e}[/red]", title="错误", border_style="red"))
            return False


def select_image_from_directory(directory):
    """让用户从目录中选择一张图片"""
    input_path = EXAMPLES_DIR / directory
    
    # 获取所有图片文件
    image_files = []
    for filename in os.listdir(input_path):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            image_files.append((filename, input_path / filename))
    
    if not image_files:
        console.print(f"[red]目录 {input_path} 中没有找到图片文件[/red]")
        return None
    
    # 显示图片列表
    console.print("\n[bold cyan]可用图片:[/bold cyan]")
    table = Table(show_header=True)
    table.add_column("序号", style="cyan", justify="right")
    table.add_column("文件名")
    table.add_column("大小", justify="right")
    
    for i, (filename, filepath) in enumerate(image_files, 1):
        size = os.path.getsize(filepath)
        size_str = f"{size / 1024:.1f} KB" if size < 1024*1024 else f"{size / (1024*1024):.1f} MB"
        table.add_row(str(i), filename, size_str)
    
    console.print(table)
    
    # 用户选择
    choice = 0
    while choice < 1 or choice > len(image_files):
        try:
            choice_str = Prompt.ask(
                "\n选择要处理的图片 [cyan](输入序号)[/cyan]", 
                default="1"
            )
            choice = int(choice_str)
            if choice < 1 or choice > len(image_files):
                console.print("[red]无效的选择，请输入有效的序号[/red]")
        except ValueError:
            console.print("[red]请输入有效的数字[/red]")
    
    selected_filename, selected_path = image_files[choice - 1]
    console.print(f"\n[green]已选择:[/green] {selected_filename}")
    
    return selected_path


def show_menu_options():
    """显示菜单选项"""
    console.print("\n[bold cyan]═══════════════════════════════════════[/bold cyan]")
    console.print("[bold]请选择操作:[/bold]")
    console.print("  [cyan]1.[/cyan] 从 input 目录选择图片上传")
    console.print("  [cyan]2.[/cyan] 指定文件路径上传")
    console.print("  [cyan]3.[/cyan] 批量上传 input 目录所有图片")
    console.print("  [cyan]q.[/cyan] 退出程序")
    console.print("[bold cyan]═══════════════════════════════════════[/bold cyan]")


async def process_batch_images(websocket, input_dir):
    """批量处理目录中的所有图片"""
    input_path = EXAMPLES_DIR / input_dir
    
    # 获取所有图片文件
    image_files = []
    for filename in os.listdir(input_path):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            image_files.append(input_path / filename)
    
    if not image_files:
        console.print(f"[red]目录 {input_path} 中没有找到图片文件[/red]")
        return
    
    console.print(f"[green]找到 {len(image_files)} 张图片，开始批量处理...[/green]")
    
    success_count = 0
    total_count = len(image_files)
    
    for i, image_path in enumerate(image_files, 1):
        console.print(f"\n[bold]处理第 {i}/{total_count} 张图片[/bold]")
        display_image_info(image_path)
        
        success = await process_single_image(websocket, image_path)
        if success:
            success_count += 1
        
        # 显示进度
        console.print(f"[dim]进度: {i}/{total_count}, 成功: {success_count}, 失败: {i - success_count}[/dim]")
    
    # 显示最终结果
    result_panel = f"""
[bold green]批量处理完成![/bold green]
总计: {total_count} 张图片
成功: {success_count} 张
失败: {total_count - success_count} 张
成功率: {(success_count / total_count * 100):.1f}%
    """
    console.print(Panel(result_panel, title="批量处理结果", border_style="green"))


async def websocket_session():
    """WebSocket会话管理"""
    console.print("[bold yellow]正在连接到服务器...[/bold yellow]")
    
    try:
        async with websockets.connect(
            SERVER_URL, 
            max_size=10 * 1024 * 1024,  # 10MB
            ping_interval=None
        ) as websocket:
            console.print("[bold green]✓ 连接成功![/bold green]")
            
            while True:
                show_menu_options()
                
                choice = Prompt.ask("\n请输入选择", default="1")
                
                if choice.lower() == 'q':
                    console.print("[yellow]正在断开连接...[/yellow]")
                    break
                elif choice == '1':
                    # 从目录选择图片
                    selected_image = select_image_from_directory("input")
                    if selected_image:
                        display_image_info(selected_image)
                        if Confirm.ask("是否处理这张图片?"):
                            await process_single_image(websocket, selected_image)
                elif choice == '2':
                    # 指定文件路径
                    file_path = Prompt.ask("请输入图片文件的完整路径")
                    image_path = Path(file_path)
                    if image_path.exists() and image_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                        display_image_info(image_path)
                        if Confirm.ask("是否处理这张图片?"):
                            await process_single_image(websocket, image_path)
                    else:
                        console.print("[red]文件不存在或不是支持的图片格式[/red]")
                elif choice == '3':
                    # 批量处理
                    if Confirm.ask("确定要批量处理 input 目录中的所有图片吗?"):
                        await process_batch_images(websocket, "input")
                else:
                    console.print("[red]无效的选择，请重试[/red]")
            
            console.print("[green]连接已断开[/green]")
            
    except Exception as e:
        console.print(Panel(f"[red]连接错误: {e}[/red]", title="连接失败", border_style="red"))


async def main():
    """主函数"""
    print_banner()
    
    console.print("[bold]欢迎使用Photo Watermark Helper WebSocket文件流客户端![/bold]")
    console.print("[dim]此版本支持持久连接和批量上传功能[/dim]")
    
    # 检查输入参数
    if len(sys.argv) > 1:
        # 如果提供了特定图片路径，使用单次连接模式
        image_path = Path(sys.argv[1])
        if image_path.exists():
            console.print(f"[green]使用命令行指定的图片:[/green] {image_path}")
            console.print("[yellow]单次连接模式，处理完毕后自动断开[/yellow]")
            
            try:
                async with websockets.connect(
                    SERVER_URL, 
                    max_size=10 * 1024 * 1024,
                    ping_interval=None
                ) as websocket:
                    display_image_info(image_path)
                    await process_single_image(websocket, image_path)
            except Exception as e:
                console.print(Panel(f"[red]连接错误: {e}[/red]", title="连接失败", border_style="red"))
        else:
            console.print(f"[red]错误: 文件 {image_path} 不存在[/red]")
    else:
        # 交互式持久连接模式
        console.print("[cyan]进入交互式模式，支持持久连接和批量操作[/cyan]")
        await websocket_session()


if __name__ == "__main__":
    # 启动异步事件循环
    asyncio.run(main())
