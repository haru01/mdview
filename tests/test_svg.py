from pathlib import Path

import pytest

from mdview.svg import SvgRenderError, apply_cjk_font, extract_svgs, rasterize_svg

FIXTURES = Path(__file__).parent / "fixtures"

_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'


def test_extract_svgs_finds_raw_block() -> None:
    svgs, prose = extract_svgs(f"説明文。\n{_SVG}\nおわり。")
    assert svgs == [_SVG]
    assert "<svg" not in prose
    assert "説明文。" in prose and "おわり。" in prose


def test_extract_svgs_unwraps_fenced_block() -> None:
    svgs, prose = extract_svgs(f"図はこちら:\n```svg\n{_SVG}\n```\n")
    assert svgs == [_SVG]
    assert "<svg" not in prose
    assert "```" not in prose  # the now-empty fence is removed
    assert "図はこちら" in prose


def test_extract_svgs_returns_text_unchanged_when_none() -> None:
    text = "ただのテキスト。SVGはない。"
    svgs, prose = extract_svgs(text)
    assert svgs == []
    assert prose == text


def test_extract_svgs_collects_multiple_in_order() -> None:
    a = _SVG.replace("rect", "circle")
    svgs, _ = extract_svgs(f"{a}\nと\n{_SVG}")
    assert svgs == [a, _SVG]


def test_apply_cjk_font_injects_important_override_after_svg_tag() -> None:
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><text font-family="Helvetica">あ</text></svg>'
    out = apply_cjk_font(svg)
    # The style block is inserted immediately after the opening <svg ...> tag.
    _, _, rest = out.partition(">")
    assert rest.lstrip().startswith("<style")
    # It forces a CJK-capable family with !important so it beats an element's
    # own font-family (cairo's toy fonts do no per-glyph fallback, so a
    # non-CJK family renders Japanese as tofu).
    assert "!important" in out
    assert "Hiragino Sans" in out
    # The original markup is preserved.
    assert '<text font-family="Helvetica">あ</text>' in out


def test_apply_cjk_font_is_noop_without_svg_tag() -> None:
    assert apply_cjk_font("plain text, no svg") == "plain text, no svg"


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
