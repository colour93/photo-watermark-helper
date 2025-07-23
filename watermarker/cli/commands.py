"""Command line interface for the watermarking tool."""

import os
import time

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.table import Table
from rich.prompt import Prompt, Confirm

from ..core.processor import WatermarkProcessor
from ..utils.config import config
from ..utils.file_utils import ensure_directory
from ..server.app import create_server


console = Console()


def print_banner():
    """Print application banner."""
    banner = """
    [bold cyan]Photo Watermark Helper[/bold cyan]
    [dim]Advanced photo watermarking tool with server and CLI support[/dim]
    """
    console.print(Panel(banner, border_style="cyan"))


class CLI:
    """Command-line interface for watermarking tool."""
    
    def __init__(self):
        """Initialize CLI."""
        self.processor = WatermarkProcessor()
    
    def process_batch(self, input_dir: str, output_dir: str, tui_mode: bool = True) -> None:
        """Process a batch of images with progress display."""
        # Ensure output directory exists
        ensure_directory(output_dir)
        
        # Get image files
        image_files = []
        for fname in os.listdir(input_dir):
            ext = os.path.splitext(fname)[1].lower()
            if ext in config.IMAGE_EXTS:
                input_path = os.path.join(input_dir, fname)
                output_path = os.path.join(output_dir, fname)
                image_files.append((fname, input_path, output_path))
        
        total_images = len(image_files)
        
        if total_images == 0:
            console.print(f"[yellow]No images found in {input_dir}[/yellow]")
            return
        
        console.print(f"[green]Found {total_images} images to process[/green]")
        
        # Process images with progress display
        processed = 0
        failed = 0
        
        if tui_mode:
            # Rich progress display
            with Progress(
                TextColumn("[bold blue]{task.description}[/bold blue]"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Processing images...", total=total_images)
                
                for fname, input_path, output_path in image_files:
                    progress.update(task, description=f"[cyan]Processing [bold]{fname}[/bold]")
                    
                    if self.processor.process_single_image(input_path, output_path):
                        processed += 1
                    else:
                        failed += 1
                    
                    progress.update(task, advance=1)
        else:
            # Simple progress display
            for i, (fname, input_path, output_path) in enumerate(image_files, 1):
                console.print(f"[{i}/{total_images}] Processing {fname}...", end="\r")
                
                if self.processor.process_single_image(input_path, output_path):
                    processed += 1
                else:
                    failed += 1
        
        # Print summary
        console.print("\n[bold green]Processing complete![/bold green]")
        console.print(f"Total images: {total_images}")
        console.print(f"Successfully processed: [green]{processed}[/green]")
        
        if failed > 0:
            console.print(f"Failed: [red]{failed}[/red]")
    
    def interactive_mode(self) -> None:
        """Run interactive TUI mode."""
        print_banner()
        
        console.print("[bold]Welcome to the interactive watermarking tool![/bold]")
        
        # Input directory
        input_dir = Prompt.ask(
            "Enter input directory path", 
            default=config.INPUT_DIR
        )
        
        # Validate input directory
        if not os.path.exists(input_dir):
            console.print(f"[red]Directory does not exist: {input_dir}[/red]")
            return
        
        # Count images
        image_count = 0
        for fname in os.listdir(input_dir):
            ext = os.path.splitext(fname)[1].lower()
            if ext in config.IMAGE_EXTS:
                image_count += 1
        
        if image_count == 0:
            console.print(f"[yellow]No images found in {input_dir}[/yellow]")
            return
        
        console.print(f"[green]Found {image_count} images to process[/green]")
        
        # Output directory
        output_dir = Prompt.ask(
            "Enter output directory path", 
            default=config.OUTPUT_DIR
        )
        
        # Confirm settings
        settings_table = Table(show_header=False, box=None)
        settings_table.add_column("Setting", style="cyan")
        settings_table.add_column("Value")
        
        settings_table.add_row("Input directory", input_dir)
        settings_table.add_row("Output directory", output_dir)
        settings_table.add_row("Images to process", str(image_count))
        settings_table.add_row("Time font", config.FONT_PATH)
        settings_table.add_row("Location font", config.LOCATION_FONT_PATH)
        
        console.print(Panel(settings_table, title="Settings", border_style="cyan"))
        
        if not Confirm.ask("Proceed with these settings?"):
            console.print("[yellow]Operation cancelled[/yellow]")
            return
        
        # Process images
        start_time = time.time()
        self.process_batch(input_dir, output_dir, tui_mode=True)
        elapsed = time.time() - start_time
        
        console.print(f"[bold green]All done in {elapsed:.2f} seconds![/bold green]")


def run_server(host: str | None = None, port: int | None = None) -> None:
    """Run the FastAPI server."""
    server = create_server()
    server.run(host=host, port=port)


@click.group()
@click.version_option()
def cli():
    """Photo Watermark Helper - Add watermarks to your photos."""
    pass


@cli.command()
@click.option("--input", "-i", help="Input directory containing images", default=config.INPUT_DIR)
@click.option("--output", "-o", help="Output directory for watermarked images", default=config.OUTPUT_DIR)
@click.option("--tui/--no-tui", default=True, help="Use rich TUI mode")
def batch(input, output, tui):
    """Process a batch of images in a directory."""
    cli_app = CLI()
    cli_app.process_batch(input, output, tui_mode=tui)


@cli.command()
def interactive():
    """Run in interactive TUI mode."""
    cli_app = CLI()
    cli_app.interactive_mode()


@cli.command()
@click.option("--host", "-h", help="Server host", default=None)
@click.option("--port", "-p", help="Server port", type=int, default=None)
def server(host, port):
    """Run as a web service with REST API and WebSocket support."""
    print_banner()
    from ..utils.config import config
    actual_host = host or config.SERVER_HOST
    actual_port = port or config.SERVER_PORT
    console.print(f"[bold green]Starting server on {actual_host}:{actual_port}[/bold green]")
    run_server(host, port)
