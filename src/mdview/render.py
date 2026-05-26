from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown


def print_markdown(path: Path) -> None:
    """Render markdown to stdout for non-TTY consumers (pipes, Claude Code, CI)."""
    text = path.read_text(encoding="utf-8")
    Console(force_terminal=False, soft_wrap=False).print(Markdown(text, code_theme="ansi_dark"))
