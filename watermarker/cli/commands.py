"""User-focused command line interface."""

from __future__ import annotations

import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import click
from PIL import ImageFont
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeRemainingColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .. import __version__
from ..core.processor import (
    POSITIONS,
    PRINT_PRESETS,
    STYLE_PRESETS,
    ProcessResult,
    WatermarkOptions,
    WatermarkProcessor,
)
from ..utils.config import config


FIELD_NAMES = ("time", "location", "camera", "lens")


def _console(ctx: click.Context | None = None) -> Console:
    settings = (ctx.find_root().obj or {}) if ctx else {}
    return Console(no_color=settings.get("no_color", False), quiet=settings.get("quiet", False))


def _parse_fields(value: str) -> tuple[str, ...]:
    fields = tuple(item.strip().lower() for item in value.split(",") if item.strip())
    invalid = set(fields) - set(FIELD_NAMES)
    if invalid:
        raise click.BadParameter(f"unknown fields: {', '.join(sorted(invalid))}")
    if not fields:
        raise click.BadParameter("at least one field is required")
    return fields


def _options(
    style: str,
    position: str,
    fields: str,
    date_format: str,
    opacity: float,
    scale: float,
    custom_time: str | None,
    custom_location: str | None,
    no_geocode: bool,
    quality: int | None,
    print_size: str | None,
    dpi: int,
    fit: str,
    safe_margin_mm: float,
    max_dimension: int | None = None,
) -> WatermarkOptions:
    return WatermarkOptions(
        style=style,
        position=position,
        fields=_parse_fields(fields),
        date_format=date_format,
        opacity=opacity,
        scale=scale,
        custom_time=custom_time,
        custom_location=custom_location,
        geocode=not no_geocode,
        quality=quality,
        max_dimension=max_dimension,
        print_size=print_size,
        dpi=dpi,
        fit=fit,
        safe_margin_mm=safe_margin_mm,
    )


def render_options(function):
    options = [
        click.option("--style", type=click.Choice(tuple(STYLE_PRESETS)), default=config.DEFAULT_STYLE, show_default=True),
        click.option("--position", type=click.Choice(POSITIONS), default=config.DEFAULT_POSITION, show_default=True),
        click.option("--fields", default="time,location", show_default=True, help="Comma-separated: time,location,camera,lens"),
        click.option("--date-format", default="%Y-%m-%d  %H:%M:%S", show_default=True),
        click.option("--opacity", type=click.FloatRange(0, 1), default=config.WATERMARK_OPACITY, show_default=True),
        click.option("--scale", type=click.FloatRange(0.4, 3), default=1.0, show_default=True),
        click.option("--time", "custom_time", help="Override the displayed time"),
        click.option("--location", "custom_location", help="Override the displayed location"),
        click.option("--no-geocode", is_flag=True, help="Use GPS coordinates without a network request"),
        click.option("--quality", type=click.IntRange(1, 100), help="JPEG/WebP output quality"),
        click.option("--print-size", type=click.Choice(tuple(PRINT_PRESETS)), help="Prepare an exact photo-print size"),
        click.option("--dpi", type=click.IntRange(72, 1200), default=300, show_default=True),
        click.option("--fit", type=click.Choice(("crop", "contain")), default="crop", show_default=True, help="Crop to fill, or keep the whole image with borders"),
        click.option("--safe-margin-mm", type=click.FloatRange(2, 20), default=5.0, show_default=True),
    ]
    for option in reversed(options):
        function = option(function)
    return function


def _destination(source: Path, output: Path, suffix: str, multiple: bool = False) -> Path:
    if not multiple and output.suffix.lower() in config.IMAGE_EXTS:
        return output
    return output / f"{source.stem}{suffix}{source.suffix.lower()}"


def _collect(directory: Path, recursive: bool) -> list[tuple[Path, Path]]:
    iterator = directory.rglob("*") if recursive else directory.glob("*")
    files = [path for path in iterator if path.is_file() and path.suffix.lower() in config.IMAGE_EXTS]
    return [(path, path.relative_to(directory)) for path in sorted(files)]


def _print_results(console: Console, results: list[ProcessResult], skipped: list[Path]) -> None:
    successes = sum(result.success for result in results)
    failures = [result for result in results if not result.success]
    console.print(
        f"[bold green]完成 {successes}[/bold green]  "
        f"[yellow]跳过 {len(skipped)}[/yellow]  "
        f"[bold red]失败 {len(failures)}[/bold red]"
    )
    if failures:
        table = Table("文件", "原因", box=None)
        for result in failures:
            table.add_row(str(result.input_path), result.error or "unknown error")
        console.print(table)
    warnings = [(result.input_path, warning) for result in results for warning in result.warnings]
    if warnings:
        table = Table("文件", "印刷提示", box=None)
        for path, warning in warnings:
            table.add_row(str(path), warning)
        console.print(table)


def _run_jobs(
    ctx: click.Context,
    jobs: list[tuple[Path, Path]],
    options: WatermarkOptions,
    workers: int,
    on_exists: str,
    dry_run: bool,
) -> tuple[list[ProcessResult], list[Path]]:
    console = _console(ctx)
    runnable: list[tuple[Path, Path]] = []
    skipped: list[Path] = []
    for source, destination in jobs:
        if destination.exists() and on_exists == "skip":
            skipped.append(destination)
            continue
        if destination.exists() and on_exists == "rename":
            index = 1
            candidate = destination
            while candidate.exists():
                candidate = destination.with_name(f"{destination.stem}-{index}{destination.suffix}")
                index += 1
            destination = candidate
        runnable.append((source, destination))

    if dry_run:
        for source, destination in runnable:
            console.print(f"{source} [dim]→[/dim] {destination}")
        console.print(f"将处理 {len(runnable)} 张，跳过 {len(skipped)} 张")
        return [], skipped

    processor = WatermarkProcessor()
    results: list[ProcessResult] = []
    root_settings = ctx.find_root().obj or {}
    show_progress = not root_settings.get("quiet") and not root_settings.get("json")
    progress = Progress(
        TextColumn("[cyan]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        disable=not show_progress,
    )
    with progress:
        task = progress.add_task("处理图片", total=len(runnable))
        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {
                executor.submit(processor.process_single_image_detailed, source, destination, options): source
                for source, destination in runnable
            }
            try:
                for future in as_completed(futures):
                    results.append(future.result())
                    progress.update(task, advance=1, description=futures[future].name)
            except KeyboardInterrupt:
                for future in futures:
                    future.cancel()
                console.print("\n[yellow]已安全中断；已完成的文件会保留。[/yellow]")
                raise click.Abort()
    return results, skipped


@click.group(invoke_without_command=True)
@click.version_option(__version__)
@click.option("--quiet", is_flag=True, help="Only emit errors")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON")
@click.option("--no-color", is_flag=True, help="Disable colored output")
@click.pass_context
def cli(ctx: click.Context, quiet: bool, json_output: bool, no_color: bool) -> None:
    """Add readable time and location watermarks to photos."""
    ctx.ensure_object(dict)
    ctx.obj.update(quiet=quiet, json=json_output, no_color=no_color)
    if ctx.invoked_subcommand is None:
        ctx.invoke(wizard)


@cli.command()
@click.argument("inputs", nargs=-1, required=True, type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--output", "output_path", "-o", type=click.Path(path_type=Path), default=Path(config.OUTPUT_DIR), show_default=True)
@click.option("--suffix", default="_watermarked", show_default=True)
@click.option("--on-exists", type=click.Choice(("skip", "rename", "overwrite")), default="skip", show_default=True)
@click.option("--workers", type=click.IntRange(1, 32), default=min(4, os.cpu_count() or 1), show_default=True)
@click.option("--dry-run", is_flag=True)
@render_options
@click.pass_context
def add(
    ctx: click.Context,
    inputs: tuple[Path, ...],
    output_path: Path,
    suffix: str,
    on_exists: str,
    workers: int,
    dry_run: bool,
    **render: object,
) -> None:
    """Process one or more image files."""
    options = _options(**render)  # type: ignore[arg-type]
    multiple = len(inputs) > 1
    if multiple and output_path.suffix.lower() in config.IMAGE_EXTS:
        raise click.UsageError("处理多个文件时，--output 必须是目录")
    jobs = [(source, _destination(source, output_path, suffix, multiple)) for source in inputs]
    results, skipped = _run_jobs(ctx, jobs, options, workers, on_exists, dry_run)
    if (ctx.find_root().obj or {}).get("json"):
        click.echo(json.dumps({"results": [item.as_dict() for item in results], "skipped": [str(path) for path in skipped]}, ensure_ascii=False))
    elif not dry_run:
        _print_results(_console(ctx), results, skipped)
    if any(not result.success for result in results):
        raise click.exceptions.Exit(1)


@cli.command()
@click.argument("input_dir", type=click.Path(path_type=Path, exists=True, file_okay=False), default=Path(config.INPUT_DIR))
@click.option("--output", "output_dir", "-o", type=click.Path(path_type=Path), default=Path(config.OUTPUT_DIR), show_default=True)
@click.option("--recursive/--no-recursive", default=False, show_default=True)
@click.option("--suffix", default="_watermarked", show_default=True)
@click.option("--on-exists", type=click.Choice(("skip", "rename", "overwrite")), default="skip", show_default=True)
@click.option("--workers", type=click.IntRange(1, 32), default=min(4, os.cpu_count() or 1), show_default=True)
@click.option("--dry-run", is_flag=True)
@render_options
@click.pass_context
def batch(
    ctx: click.Context,
    input_dir: Path,
    output_dir: Path,
    recursive: bool,
    suffix: str,
    on_exists: str,
    workers: int,
    dry_run: bool,
    **render: object,
) -> None:
    """Process an image directory, optionally preserving nested folders."""
    discovered = _collect(input_dir, recursive)
    try:
        resolved_output = output_dir.resolve()
        resolved_input = input_dir.resolve()
        if resolved_output == resolved_input:
            discovered = [item for item in discovered if not item[0].stem.endswith(suffix)]
        elif resolved_output.is_relative_to(resolved_input):
            discovered = [
                item for item in discovered if not item[0].resolve().is_relative_to(resolved_output)
            ]
    except OSError:
        pass
    if not discovered:
        raise click.ClickException(f"在 {input_dir} 中没有找到支持的图片")
    jobs = [
        (source, output_dir / relative.parent / f"{source.stem}{suffix}{source.suffix.lower()}")
        for source, relative in discovered
    ]
    options = _options(**render)  # type: ignore[arg-type]
    results, skipped = _run_jobs(ctx, jobs, options, workers, on_exists, dry_run)
    if (ctx.find_root().obj or {}).get("json"):
        click.echo(json.dumps({"results": [item.as_dict() for item in results], "skipped": [str(path) for path in skipped]}, ensure_ascii=False))
    elif not dry_run:
        _print_results(_console(ctx), results, skipped)
    if any(not result.success for result in results):
        raise click.exceptions.Exit(1)


@cli.command()
@click.argument("image", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--output", "output_path", "-o", type=click.Path(path_type=Path))
@click.option("--open/--no-open", "open_result", default=False, help="Open the preview with the system viewer")
@render_options
@click.pass_context
def preview(ctx: click.Context, image: Path, output_path: Path | None, open_result: bool, **render: object) -> None:
    """Create a fast, reduced-size preview."""
    output_path = output_path or image.with_name(f"{image.stem}.preview.jpg")
    options = _options(max_dimension=1800, **render)  # type: ignore[arg-type]
    result = WatermarkProcessor().process_single_image_detailed(image, output_path, options)
    if not result.success:
        raise click.ClickException(result.error or "preview failed")
    if (ctx.find_root().obj or {}).get("json"):
        click.echo(json.dumps(result.as_dict(), ensure_ascii=False))
    else:
        _console(ctx).print(f"预览已生成：[link={output_path.resolve()}]{output_path}[/link]")
    if open_result:
        click.launch(str(output_path.resolve()))


@cli.command(name="inspect")
@click.argument("images", nargs=-1, required=True, type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--no-geocode", is_flag=True)
@click.pass_context
def inspect_command(ctx: click.Context, images: tuple[Path, ...], no_geocode: bool) -> None:
    """Inspect the metadata that will be used in a watermark."""
    processor = WatermarkProcessor()
    records = [{"file": str(path), **processor.inspect_image(path, geocode=not no_geocode).as_dict()} for path in images]
    if (ctx.find_root().obj or {}).get("json"):
        click.echo(json.dumps(records, ensure_ascii=False))
        return
    console = _console(ctx)
    for record in records:
        table = Table(show_header=False, box=None)
        for key, value in record.items():
            table.add_row(key, str(value) if value is not None else "—")
        console.print(Panel(table, title=Path(str(record["file"])).name))


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check local configuration, fonts, and optional server dependencies."""
    checks: list[tuple[str, bool, str]] = []
    checks.append(("输入目录", Path(config.INPUT_DIR).is_dir(), config.INPUT_DIR))
    checks.append(("输出目录", Path(config.OUTPUT_DIR).parent.exists(), config.OUTPUT_DIR))
    checks.append(("高德 API", bool(config.AMAP_API_KEY), "已配置" if config.AMAP_API_KEY else "未配置，将显示坐标"))
    for label, configured in (
        ("时间字体", config.FONT_PATH),
        ("地点字体", config.LOCATION_FONT_PATH),
    ):
        configured_ok = bool(configured and Path(configured).is_file())
        fallback_ok = configured_ok
        if not fallback_ok:
            for candidate in WatermarkProcessor._font_candidates(configured):
                try:
                    ImageFont.truetype(candidate, 16)
                    fallback_ok = True
                    break
                except OSError:
                    continue
        detail = configured if configured_ok else f"{configured or '未配置'}（将回退系统字体）"
        checks.append((label, configured_ok, detail if fallback_ok else "没有可用字体"))
    server_ok = all(importlib.util.find_spec(name) for name in ("fastapi", "uvicorn", "aiofiles"))
    checks.append(("服务端 extra", server_ok, "uv sync --extra server" if not server_ok else "已安装"))
    if (ctx.find_root().obj or {}).get("json"):
        click.echo(json.dumps([{"name": name, "ok": ok, "detail": detail} for name, ok, detail in checks], ensure_ascii=False))
    else:
        table = Table("检查项", "状态", "说明")
        for name, ok, detail in checks:
            table.add_row(name, "[green]OK[/green]" if ok else "[yellow]注意[/yellow]", detail)
        _console(ctx).print(table)


@cli.group(name="config")
def config_command() -> None:
    """Show or create dotenv configuration."""


@config_command.command(name="show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show effective configuration."""
    values = config.as_dict()
    if (ctx.find_root().obj or {}).get("json"):
        click.echo(json.dumps(values, ensure_ascii=False, default=str))
        return
    table = Table("配置", "值")
    for key, value in sorted(values.items()):
        if "TOKEN" in key or "KEY" in key:
            value = "已配置" if value else "未配置"
        table.add_row(key, str(value))
    _console(ctx).print(table)


@config_command.command(name="init")
@click.option("--path", "config_path", type=click.Path(path_type=Path), default=Path(".env"), show_default=True)
@click.option("--force", is_flag=True)
def config_init(config_path: Path, force: bool) -> None:
    """Create a documented starter .env file."""
    if config_path.exists() and not force:
        raise click.ClickException(f"{config_path} 已存在；使用 --force 覆盖")
    template = Path(__file__).resolve().parents[1] / "default.env"
    if not template.is_file():
        raise click.ClickException("安装包中没有 .env.example，请手动创建配置")
    config_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    click.echo(f"已创建 {config_path}")


@cli.command()
@click.pass_context
def wizard(ctx: click.Context) -> None:
    """Guide a first-time user through a safe batch run."""
    console = _console(ctx)
    console.print(Panel("[bold cyan]Photo Watermark Helper[/bold cyan]\n预览并安全批量添加照片水印"))
    input_dir = Path(Prompt.ask("照片目录", default=config.INPUT_DIR)).expanduser()
    if not input_dir.is_dir():
        raise click.ClickException(f"目录不存在：{input_dir}")
    output_dir = Path(Prompt.ask("输出目录", default=config.OUTPUT_DIR)).expanduser()
    print_mode = Confirm.ask("是否开启照片冲印模式？", default=False)
    print_size = None
    dpi = 300
    fit = "crop"
    safe_margin_mm = 5.0
    if print_mode:
        print_size = Prompt.ask(
            "冲印尺寸（英寸）",
            choices=list(PRINT_PRESETS),
            default="4x6",
        )
        fit = Prompt.ask(
            "画面适配（crop=裁切铺满，contain=完整保留并留边）",
            choices=["crop", "contain"],
            default="crop",
        )
        console.print(
            "将按 [bold]300 DPI[/bold] 输出，保留 [bold]5 mm[/bold] 安全边距；"
            "水印会在最终裁切后定位。"
        )
    style = Prompt.ask(
        "水印样式",
        choices=list(STYLE_PRESETS),
        default="retro" if print_mode else config.DEFAULT_STYLE,
    )
    discovered = _collect(input_dir, recursive=False)
    console.print(f"找到 [bold]{len(discovered)}[/bold] 张图片，默认不会覆盖已存在文件。")
    if not discovered or not Confirm.ask("开始处理？", default=True):
        return
    ctx.invoke(
        batch,
        input_dir=input_dir,
        output_dir=output_dir,
        recursive=False,
        suffix="_watermarked",
        on_exists="skip",
        workers=min(4, os.cpu_count() or 1),
        dry_run=False,
        style=style,
        position=config.DEFAULT_POSITION,
        fields="time,location",
        date_format="%Y-%m-%d  %H:%M:%S",
        opacity=config.WATERMARK_OPACITY,
        scale=1.0,
        custom_time=None,
        custom_location=None,
        no_geocode=False,
        quality=None,
        print_size=print_size,
        dpi=dpi,
        fit=fit,
        safe_margin_mm=safe_margin_mm,
    )


@cli.command()
@click.option("--host", help="Server host", default=None)
@click.option("--port", type=int, default=None)
def server(host: str | None, port: int | None) -> None:
    """Run the optional REST/WebSocket service."""
    try:
        from ..server.app import create_server
    except ImportError as exc:
        raise click.ClickException("服务端依赖未安装，请运行：uv sync --extra server") from exc
    create_server().run(host=host, port=port)


# Compatibility with the previous command name.
cli.add_command(wizard, name="interactive")
