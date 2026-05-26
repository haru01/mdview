"""SVG to PNG rasterization, isolated so it can be tested without a TUI."""

from __future__ import annotations

import os
from pathlib import Path

_MAC_LIB_DIRS = (
    "/opt/homebrew/lib",  # macOS Apple Silicon
    "/usr/local/lib",  # macOS Intel
    "/opt/local/lib",  # MacPorts
)


def _ensure_lib_search_path() -> None:
    """macOS の dyld は /opt/homebrew/lib を既定で見ない。cairosvg が import される
    前に DYLD_FALLBACK_LIBRARY_PATH を補強しておく。"""
    existing = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    paths = [p for p in existing.split(":") if p]
    for d in _MAC_LIB_DIRS:
        if os.path.isdir(d) and d not in paths:
            paths.append(d)
    if paths:
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(paths)


class SvgRenderError(RuntimeError):
    pass


def rasterize_svg(src: Path, dst: Path, *, width_px: int) -> Path:
    if not src.exists():
        raise FileNotFoundError(src)

    _ensure_lib_search_path()
    try:
        import cairosvg
    except (ImportError, OSError) as e:
        raise SvgRenderError(f"cairosvg unavailable: {e}") from e

    try:
        cairosvg.svg2png(
            url=str(src),
            write_to=str(dst),
            output_width=width_px,
        )
    except Exception as e:
        raise SvgRenderError(f"failed to render {src}: {e}") from e

    return dst
