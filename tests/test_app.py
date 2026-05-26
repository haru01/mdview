from __future__ import annotations

from pathlib import Path

import pytest

from mdview.app import MdViewerApp, _paragraph_image_src

FIXTURES = Path(__file__).parent / "fixtures"


def test_sample_svg_paragraph_is_replaced_with_image_widget() -> None:
    """Smoke test: app launches, loads the sample, replaces a paragraph with an Image."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:  # noqa: D401

        app = MdViewerApp(md)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            from textual_image.widget import Image
            from textual.widgets._markdown import MarkdownParagraph

            # Image widget must have been injected from the SVG reference.
            images = list(app.query(Image))
            assert images, "expected at least one Image widget for sample.svg"

            # No remaining MarkdownParagraph should contain only the SVG image.
            for paragraph in app.query(MarkdownParagraph):
                assert _paragraph_image_src(paragraph) is None

    asyncio.run(driver())


def test_n_and_p_navigate_between_headings() -> None:
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()

            from textual.widgets import MarkdownViewer

            viewer = app.query_one(MarkdownViewer)
            start = viewer.scroll_y

            await pilot.press("n")
            await pilot.pause()
            after_first_n = viewer.scroll_y
            assert after_first_n > start, "`n` should move scroll down to next heading"

            await pilot.press("n")
            await pilot.pause()
            after_second_n = viewer.scroll_y
            assert after_second_n > after_first_n, "`n` should advance further"

            await pilot.press("p")
            await pilot.pause()
            after_p = viewer.scroll_y
            assert after_p < after_second_n, "`p` should move back to previous heading"

    asyncio.run(driver())


def test_table_widget_is_rendered() -> None:
    """Sample has a markdown table; Textual must materialize it as MarkdownTable."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            from textual.widgets._markdown import MarkdownTable

            tables = list(app.query(MarkdownTable))
            assert tables, "expected at least one MarkdownTable widget"
            t = tables[0]
            assert [str(h) for h in t._headers] == ["Key", "Value"]
            assert len(t._rows) == 3

    asyncio.run(driver())


def test_anchor_link_scrolls_to_section() -> None:
    """`#mermaid` anchor click via LinkClicked must scroll the viewer."""
    import asyncio

    from textual.widgets import Markdown, MarkdownViewer

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            doc = viewer.document
            before = viewer.scroll_y
            doc.post_message(Markdown.LinkClicked(doc, "#mermaid"))
            await pilot.pause()
            await pilot.pause()
            assert viewer.scroll_y > before, "anchor click should scroll down"

    asyncio.run(driver())


def test_markdown_link_navigates_to_other_file() -> None:
    """Clicking `[..](other.md)` should load the other markdown file."""
    import asyncio

    from textual.widgets import Markdown, MarkdownViewer

    md = FIXTURES / "link_a.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            doc = viewer.document
            assert app._md_path.name == "link_a.md"

            doc.post_message(Markdown.LinkClicked(doc, "link_b.md"))
            for _ in range(10):
                await pilot.pause()
                if app._md_path.name == "link_b.md":
                    break
            assert app._md_path.name == "link_b.md"
            assert app.title == "link_b.md"

    asyncio.run(driver())


def test_markdown_link_with_anchor_jumps_to_section() -> None:
    """`other.md#anchor` loads file and jumps to anchor."""
    import asyncio

    from textual.widgets import Markdown, MarkdownViewer

    md = FIXTURES / "link_a.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            doc = viewer.document

            doc.post_message(Markdown.LinkClicked(doc, "link_b.md#section-two"))
            for _ in range(20):
                await pilot.pause()
                if app._md_path.name == "link_b.md" and viewer.scroll_y > 0:
                    break
            assert app._md_path.name == "link_b.md"
            # anchor jump should scroll past the top of the document
            assert viewer.scroll_y > 0

    asyncio.run(driver())


def test_back_returns_to_previous_file() -> None:
    """`b` keybinding pops history and reloads the prior file."""
    import asyncio

    from textual.widgets import Markdown, MarkdownViewer

    md = FIXTURES / "link_a.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            doc = viewer.document

            doc.post_message(Markdown.LinkClicked(doc, "link_b.md"))
            for _ in range(10):
                await pilot.pause()
                if app._md_path.name == "link_b.md":
                    break
            assert app._md_path.name == "link_b.md"

            await pilot.press("b")
            for _ in range(10):
                await pilot.pause()
                if app._md_path.name == "link_a.md":
                    break
            assert app._md_path.name == "link_a.md"

    asyncio.run(driver())


def test_stdin_content_loads_and_titles() -> None:
    """Content passed in (as from piped stdin) renders and titles as (stdin)."""
    import asyncio

    from textual.widgets import MarkdownViewer

    async def driver() -> None:
        app = MdViewerApp(content="# Piped\n\nHello from stdin.")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app.title == "(stdin)"
            assert app._md_dir == Path.cwd()
            viewer = app.query_one(MarkdownViewer)
            assert "Piped" in viewer.document.source

    asyncio.run(driver())


def test_stdin_base_dir_overrides_resolution_root(tmp_path: Path) -> None:
    """base_dir sets where relative images/links resolve for stdin content."""
    import asyncio

    async def driver() -> None:
        app = MdViewerApp(content="# x", base_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app._md_dir == tmp_path.resolve()

    asyncio.run(driver())


def test_mermaid_fence_replaced_when_mmdc_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a fake mmdc on PATH, mermaid fences become Image widgets."""
    import asyncio
    import shutil
    import textwrap

    from tests.test_mermaid import _fake_mmdc  # reuse the bash stub

    mmdc = _fake_mmdc(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(mmdc, bindir / "mmdc")
    (bindir / "mmdc").chmod(0o755)
    import os

    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            from textual.widgets._markdown import MarkdownFence
            from textual_image.widget import Image

            mermaid_fences = [
                f for f in app.query(MarkdownFence) if f.lexer == "mermaid"
            ]
            assert not mermaid_fences, "mermaid fence should be replaced"
            assert list(app.query(Image)), "an Image widget should exist"

    _ = textwrap  # silence unused import; kept for clarity
    asyncio.run(driver())
