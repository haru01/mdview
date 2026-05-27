"""SVG to PNG rasterization, isolated so it can be tested without a TUI."""

from __future__ import annotations

import os
import re
from pathlib import Path

# Matches a whole `<svg>…</svg>` element (lazy, so adjacent diagrams stay
# separate). DOTALL lets the body span lines; IGNORECASE tolerates `<SVG>`.
_SVG_RE = re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE)
# An empty fenced code block left behind once its SVG body is pulled out.
_EMPTY_FENCE_RE = re.compile(r"```[a-zA-Z]*\s*```")


def extract_svgs(text: str) -> tuple[list[str], str]:
    """Split SVG diagrams out of an AI answer.

    Returns the `<svg>…</svg>` blocks (in order, whether raw or wrapped in a
    ```svg fence) and the remaining prose with those blocks — and any fence that
    only held them — removed. When there is no SVG, the text is returned as-is.
    """
    svgs = _SVG_RE.findall(text)
    if not svgs:
        return [], text
    remaining = _SVG_RE.sub("", text)
    remaining = _EMPTY_FENCE_RE.sub("", remaining)
    remaining = re.sub(r"\n{3,}", "\n\n", remaining).strip()
    return svgs, remaining


# Matches the opening `<svg ...>` tag (attributes may span lines; `[^>]` covers
# newlines). Used to splice a stylesheet in right after it.
_SVG_OPEN_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
# A CJK-capable font stack: Hiragino on macOS, Noto on Linux, with sans-serif as
# the last resort. The first installed family wins.
_CJK_FONT_STACK = (
    '"Hiragino Sans", "Hiragino Kaku Gothic ProN", "Arial Unicode MS", '
    '"BIZ UDGothic", "Noto Sans CJK JP", "Noto Sans JP", sans-serif'
)
_CJK_FONT_STYLE = f"<style>text,tspan{{font-family:{_CJK_FONT_STACK} !important;}}</style>"


def apply_cjk_font(svg: str) -> str:
    """Force a CJK-capable font on every text element of an SVG.

    cairo's toy font API picks a single face per text run and does no per-glyph
    fallback, so an SVG whose ``font-family`` lacks Japanese glyphs renders
    Japanese as tofu (□). We splice an override stylesheet in right after the
    opening ``<svg>`` tag; ``!important`` lets it beat each element's own
    ``font-family``. Returns the input unchanged if it has no usable ``<svg>``
    tag (e.g. a self-closing root with no text to style).
    """
    match = _SVG_OPEN_RE.search(svg)
    if match is None or match.group().rstrip().endswith("/>"):
        return svg
    end = match.end()
    return svg[:end] + _CJK_FONT_STYLE + svg[end:]

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
        raise SvgRenderError(f"svg source not found: {src}")

    _ensure_lib_search_path()
    try:
        import cairosvg
    except (ImportError, OSError) as e:
        raise SvgRenderError(f"cairosvg unavailable: {e}") from e

    try:
        markup = apply_cjk_font(src.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        raise SvgRenderError(f"failed to read {src}: {e}") from e

    try:
        # bytestring carries the CJK-patched markup; url keeps the file's
        # directory as the base for any relative references inside the SVG.
        cairosvg.svg2png(
            bytestring=markup.encode("utf-8"),
            url=str(src),
            write_to=str(dst),
            output_width=width_px,
        )
    except Exception as e:
        raise SvgRenderError(f"failed to render {src}: {e}") from e

    return dst
