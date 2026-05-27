from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from mdview.diff import FileDiff
from mdview.diffview import render_diff


def print_markdown(path: Path) -> None:
    """Render markdown to stdout for non-TTY consumers (pipes, Claude Code, CI)."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Fall back to latin-1 (lossless byte→codepoint mapping) so we still
        # emit something readable instead of crashing on non-UTF-8 input.
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"mdview: failed to read {path}: {e}", file=sys.stderr)
            return
    print_markdown_text(text)


def print_markdown_text(text: str) -> None:
    """Render an in-memory markdown string to stdout (used for piped stdin)."""
    Console(force_terminal=False, soft_wrap=False).print(Markdown(text, code_theme="ansi_dark"))


def print_diff(files: list[FileDiff]) -> None:
    """Render a parsed diff in the delta-like style for non-TTY consumers.

    Reuses the same hunk renderer as the TUI, so a piped diff (`git diff |
    mdview`) keeps the line-number gutters, +/- markers and file banners; colour
    follows Rich's usual auto-detection (dropped when stdout is not a terminal).
    """
    Console(force_terminal=False, soft_wrap=False).print(render_diff(files))
