from __future__ import annotations

from pathlib import Path

from mdview.image_zoom import ZoomableImage
from mdview.svg_widgets import svg_to_zoomable_image

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="30">'
    '<rect width="80" height="30" fill="#4ebf71"/></svg>'
)


def test_svg_to_zoomable_image_writes_files_and_returns_widget(tmp_path: Path) -> None:
    """Valid SVG markup is persisted (under the given prefix), rasterized to PNG,
    and returned as a clickable ZoomableImage."""
    widget = svg_to_zoomable_image(_SVG, tmp_path, width_hint=200, prefix="ask-ai")
    assert isinstance(widget, ZoomableImage)
    assert list(tmp_path.glob("ask-ai-*.svg")), "svg markup persisted under the prefix"
    assert list(tmp_path.glob("ask-ai-*.png")), "rasterized png written"


def test_svg_to_zoomable_image_returns_none_on_bad_svg(tmp_path: Path) -> None:
    """A failed rasterization degrades to None rather than raising."""
    assert svg_to_zoomable_image("not an svg at all", tmp_path, width_hint=200) is None
