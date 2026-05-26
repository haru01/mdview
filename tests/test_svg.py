from pathlib import Path

import pytest

from mdview.svg import SvgRenderError, rasterize_svg

FIXTURES = Path(__file__).parent / "fixtures"


def test_rasterize_writes_png(tmp_path: Path) -> None:
    out = tmp_path / "out.png"
    rasterize_svg(FIXTURES / "sample.svg", out, width_px=400)
    assert out.exists()
    assert out.stat().st_size > 0
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(SvgRenderError):
        rasterize_svg(tmp_path / "missing.svg", tmp_path / "out.png", width_px=200)


def test_invalid_svg_raises_render_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.svg"
    bad.write_text("<not-svg>nope</not-svg>")
    with pytest.raises(SvgRenderError):
        rasterize_svg(bad, tmp_path / "out.png", width_px=200)
