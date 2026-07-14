"""Application entry point."""

from __future__ import annotations

from .cli.commands import cli


def main() -> None:
    """Run the command line application."""
    cli()


if __name__ == "__main__":
    main()
