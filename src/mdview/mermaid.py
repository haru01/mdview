"""Render mermaid diagrams via the mermaid-cli (`mmdc`) tool.

Isolated from the TUI so it can be unit tested without textual.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class MermaidRenderError(RuntimeError):
    pass


def find_mmdc() -> str | None:
    """Return the absolute path to a `mmdc` executable, or None if absent."""
    return shutil.which("mmdc")


def render_mermaid(
    code: str,
    dst: Path,
    *,
    mmdc: str,
    width: int = 1600,
    timeout: float = 30.0,
) -> Path:
    """Render `code` to `dst` using mmdc. Output format is chosen by `dst` suffix.

    Prefer .png — mmdc rasterizes via real Chromium and handles the <foreignObject>
    labels that flowchart-v2 emits. Going through .svg + cairosvg drops those
    labels (cairosvg ignores foreignObject), leaving shapes without text.

    Raises MermaidRenderError on any failure (missing binary, non-zero exit,
    empty output file).
    """
    src = dst.with_suffix(".mmd")
    src.write_text(code, encoding="utf-8")
    try:
        proc = subprocess.run(
            [
                mmdc,
                "-i", str(src),
                "-o", str(dst),
                "-b", "transparent",
                "-w", str(width),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as e:
        raise MermaidRenderError(f"mmdc not found: {mmdc}") from e
    except subprocess.TimeoutExpired as e:
        raise MermaidRenderError(f"mmdc timed out after {timeout}s") from e

    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise MermaidRenderError(f"mmdc exited {proc.returncode}: {stderr}")
    if not dst.exists() or dst.stat().st_size == 0:
        raise MermaidRenderError(f"mmdc produced no output at {dst}")
    return dst
