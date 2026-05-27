"""Turn SVG markup into rendered, click-to-zoom image widgets.

The thin Textual wrapper over the pure `svg.py` rasterizer: it persists SVG
markup to a temp file, rasterizes it to PNG, and wraps the result in a
`ZoomableImage`. Shared by the Ask AI popup (`ask_ai.py`) and the section-insight
popup (`section_insight.py`) so both render diagrams the same way.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from textual.containers import ScrollableContainer
from textual.widget import Widget

from mdview.image_zoom import ZoomableImage
from mdview.svg import SvgRenderError, rasterize_svg


def svg_to_zoomable_image(
    svg: str, tmpdir: Path, *, width_hint: int, prefix: str = "svg"
) -> ZoomableImage | None:
    """Persist ``svg`` markup under ``tmpdir`` and return it as a `ZoomableImage`.

    The markup (and its PNG) are keyed by a hash of the markup, so identical
    diagrams reuse the same files. ``prefix`` names the file stem so callers can
    keep their scratch files distinguishable. Returns ``None`` if rasterization
    fails, so a bad diagram is skipped rather than raising.
    """
    digest = hashlib.sha1(svg.encode("utf-8")).hexdigest()[:12]
    svg_path = tmpdir / f"{prefix}-{digest}.svg"
    png_path = tmpdir / f"{prefix}-{digest}.png"
    svg_path.write_text(svg, encoding="utf-8")
    try:
        rasterize_svg(svg_path, png_path, width_px=width_hint)
    except SvgRenderError:
        return None
    return ZoomableImage(png_path)


async def render_svgs_into(
    scroll: ScrollableContainer,
    svgs: list[str],
    tmpdir: Path,
    *,
    width_hint: int,
    before: Widget | None = None,
    prefix: str = "svg",
) -> int:
    """Rasterize each SVG in ``svgs`` and mount it into ``scroll``; return the
    count shown. When ``before`` is given, diagrams mount ahead of it (so a
    figure can lead the prose that follows). Unrenderable SVGs are skipped."""
    rendered = 0
    for svg in svgs:
        widget = svg_to_zoomable_image(svg, tmpdir, width_hint=width_hint, prefix=prefix)
        if widget is None:
            continue
        if before is not None:
            await scroll.mount(widget, before=before)
        else:
            await scroll.mount(widget)
        rendered += 1
    return rendered
