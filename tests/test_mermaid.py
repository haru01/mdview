from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from mdview.mermaid import MermaidRenderError, render_mermaid

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_mmdc(tmp_path: Path, *, exit_code: int = 0, write_output: bool = True) -> Path:
    """Create a fake `mmdc` shell script.

    Picks a payload by the `-o` argument suffix: `.svg` → sample SVG,
    `.png` → 1x1 transparent PNG. Mirrors the real mmdc which infers format
    from the output extension.
    """
    svg_payload = (FIXTURES / "sample.svg").read_text(encoding="utf-8")
    svg_file = tmp_path / "payload.svg"
    svg_file.write_text(svg_payload, encoding="utf-8")

    import base64
    png_bytes = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    png_file = tmp_path / "payload.png"
    png_file.write_bytes(png_bytes)

    script = tmp_path / "mmdc"
    body = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        # parse `-o <path>` out of the arguments
        out=""
        while [ "$#" -gt 0 ]; do
          case "$1" in
            -o) out="$2"; shift 2;;
            *) shift;;
          esac
        done
        if {"true" if write_output else "false"}; then
          case "$out" in
            *.png) cp "{png_file}" "$out";;
            *)     cp "{svg_file}" "$out";;
          esac
        fi
        exit {exit_code}
        """
    )
    script.write_text(body)
    script.chmod(0o755)
    return script


def test_render_mermaid_writes_svg(tmp_path: Path) -> None:
    mmdc = _fake_mmdc(tmp_path)
    out = tmp_path / "diagram.svg"
    render_mermaid("flowchart LR\n  A --> B\n", out, mmdc=str(mmdc))
    assert out.exists()
    assert out.stat().st_size > 0


def test_render_mermaid_nonzero_exit_raises(tmp_path: Path) -> None:
    mmdc = _fake_mmdc(tmp_path, exit_code=2, write_output=False)
    with pytest.raises(MermaidRenderError):
        render_mermaid("garbage", tmp_path / "x.svg", mmdc=str(mmdc))


def test_render_mermaid_missing_binary_raises(tmp_path: Path) -> None:
    with pytest.raises(MermaidRenderError):
        render_mermaid("x", tmp_path / "x.svg", mmdc=str(tmp_path / "does-not-exist"))
