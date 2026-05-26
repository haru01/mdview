from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown


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
    Console(force_terminal=False, soft_wrap=False).print(Markdown(text, code_theme="ansi_dark"))
