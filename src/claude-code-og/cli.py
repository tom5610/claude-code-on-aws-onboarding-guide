#!/usr/bin/env python3

"""
CLI entry point for claude-code-helper using Typer.
"""

import typer
from typing import Optional
from rich.console import Console

from .commands import admin_app, client_app

# Create main Typer app
app = typer.Typer(
    help="Claude Code on AWS helper scripts.",
    rich_markup_mode="rich",
)

# Add subcommands
app.add_typer(
    admin_app.app,
    name="admin",
    help="Admin commands for setting up application inference profiles on Amazon Bedrock.",
)

app.add_typer(
    client_app.app,
    name="client",
    help="Client commands for configuring Claude Code on AWS.",
)

console = Console()

def version_callback(value: bool):
    """Print version and exit."""
    if value:
        from importlib.metadata import version
        try:
            v = version("claude-code-on-aws-onboarding-guide")
            console.print(f"Claude Code on AWS Onboard Guide: [bold green]{v}[/]")
        except:
            console.print("[yellow]Package version information not available[/]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", help="Show the application version and exit.", callback=version_callback
    ),
):
    """
    Claude Code on AWS Onboard Guide - CLI tool for setting up and using
    Amazon Bedrock for Claude Code.
    """
    pass


if __name__ == "__main__":
    app()