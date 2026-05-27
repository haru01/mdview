from __future__ import annotations

import asyncio
from pathlib import Path

from textual.selection import SELECT_ALL
from textual.widgets import MarkdownViewer
from textual.widgets._markdown import (
    MarkdownHeader,
    MarkdownParagraph,
    MarkdownTable,
)

from mdview.app import MdViewerApp
from mdview.selection import build_scopes, find_leaf_block

FIXTURES = Path(__file__).parent / "fixtures"


def _para(doc, text: str) -> MarkdownParagraph:
    for p in doc.query(MarkdownParagraph):
        if text in str(p._render()):
            return p
    raise AssertionError(f"no paragraph containing {text!r}")


def _heading(doc, text: str) -> MarkdownHeader:
    for h in doc.query(MarkdownHeader):
        if text in str(h._render()):
            return h
    raise AssertionError(f"no heading containing {text!r}")


def _selected_text(screen, roots) -> str:
    """Apply a scope (list of root widgets) and return the resulting text."""
    sel = {}
    for root in roots:
        sel[root] = SELECT_ALL
        for descendant in root.query("*"):
            sel[descendant] = SELECT_ALL
    screen.selections = sel
    return screen.get_selected_text() or ""


def _run(driver) -> None:
    async def main() -> None:
        app = MdViewerApp(FIXTURES / "sample.md")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            doc = app.query_one(MarkdownViewer).document
            await driver(app, doc)

    asyncio.run(main())


def test_find_leaf_block_resolves_clicked_descendant() -> None:
    """A click on a block, its container, a table, or a non-block resolves correctly."""

    async def driver(app, doc) -> None:
        para = _para(doc, "箇条書き 1")
        # self is already an atomic block
        assert find_leaf_block(para) is para
        # a container (the item's Vertical) descends to its inner block
        assert find_leaf_block(para.parent) is para
        # a table click resolves to the whole MarkdownTable, not its content widget
        leaf = find_leaf_block(doc.query(MarkdownTable).first())
        assert isinstance(leaf, MarkdownTable)
        # a non-markdown widget (the injected image) is not a block
        from mdview.image_zoom import ZoomableImage

        images = list(app.query(ZoomableImage))
        if images:
            assert find_leaf_block(images[0]) is None
        # a click on the document background (not inside any block) selects nothing
        assert find_leaf_block(doc) is None
        assert find_leaf_block(app.screen) is None

    _run(driver)


def test_build_scopes_expands_list_paragraph_through_structure() -> None:
    """block ⊂ list item ⊂ list ⊂ section ⊂ document, each step strictly larger."""

    async def driver(app, doc) -> None:
        para = _para(doc, "箇条書き 1")
        scopes = build_scopes(para, doc)
        texts = [_selected_text(app.screen, roots) for roots in scopes]

        # Monotonic growth, each rung containing the previous selection's text.
        for smaller, larger in zip(texts, texts[1:]):
            assert len(larger) > len(smaller), (smaller, larger)

        # First rung is just the clicked list item's text.
        assert texts[0].strip() == "箇条書き 1"
        # Some rung selects the whole bullet list (all items incl. nested),
        # but not the sibling ordered list.
        assert any(
            "箇条書き 1" in t and "箇条書き 3" in t and "ネスト 2" in t and "順序付き" not in t
            for t in texts
        )
        # Some rung is the whole "リスト" section: both lists, no other section.
        assert any(
            "順序付き 3" in t and "コードブロック" not in t and "mdview サンプル" not in t
            for t in texts
        )
        # Final rung is the entire document.
        assert "mdview サンプル" in texts[-1] and "これでサンプルは終わり" in texts[-1]

    _run(driver)


def test_build_scopes_heading_expands_to_its_section() -> None:
    """Clicking a heading expands to its whole section, then the document."""

    async def driver(app, doc) -> None:
        heading = _heading(doc, "リスト")
        scopes = build_scopes(heading, doc)
        texts = [_selected_text(app.screen, roots) for roots in scopes]

        assert texts[0].strip() == "リスト"
        # A rung covers the section (both lists) but not neighbouring sections.
        assert any(
            "箇条書き 1" in t and "順序付き 3" in t and "コードブロック" not in t for t in texts
        )
        assert "mdview サンプル" in texts[-1]

    _run(driver)


def test_build_scopes_plain_paragraph_has_no_container_rung() -> None:
    """A top-level paragraph collapses to exactly: block, section, document."""

    async def driver(app, doc) -> None:
        para = _para(doc, "これは普通の段落")
        scopes = build_scopes(para, doc)
        texts = [_selected_text(app.screen, roots) for roots in scopes]

        assert len(scopes) == 3, [t[:20] for t in texts]
        # block: the paragraph only (no heading)
        assert "太字" in texts[0] and "段落と強調" not in texts[0]
        # section: includes the governing heading
        assert "段落と強調" in texts[1] and "太字" in texts[1]
        # document
        assert "mdview サンプル" in texts[2]
        for smaller, larger in zip(texts, texts[1:]):
            assert len(larger) > len(smaller)

    _run(driver)


def test_section_source_returns_only_that_sections_markdown() -> None:
    """`section_source` returns the heading line and its body as raw Markdown,
    bounded by the next equal-or-higher heading (here: the next `##`)."""
    from mdview.selection import section_source

    async def driver(app, doc) -> None:
        heading = _heading(doc, "リスト")
        src = section_source(heading, doc)
        assert src.startswith("## リスト"), src[:40]
        # the section body is included...
        assert "箇条書き 1" in src
        assert "順序付き 3" in src
        # ...but neighbouring sections are not.
        assert "コードブロック" not in src
        assert "段落と強調" not in src

    _run(driver)


def test_section_line_range_slices_the_same_text_as_section_source() -> None:
    """`section_line_range` indexes the source so slicing it equals `section_source`."""
    from mdview.selection import section_line_range, section_source

    async def driver(app, doc) -> None:
        heading = _heading(doc, "リスト")
        span = section_line_range(heading, doc)
        assert span is not None
        start, end = span
        lines = doc.source.splitlines(keepends=True)
        assert "".join(lines[start:end]) == section_source(heading, doc)

    _run(driver)


def test_section_source_last_section_runs_to_end_of_document() -> None:
    """The final `##` section extends to the end of the document."""
    from mdview.selection import section_source

    async def driver(app, doc) -> None:
        heading = _heading(doc, "Mermaid")
        src = section_source(heading, doc)
        assert src.startswith("## Mermaid"), src[:40]
        assert "これでサンプルは終わり" in src

    _run(driver)


def test_section_source_h2_includes_its_subsections() -> None:
    """An H2 section absorbs its deeper (H3–H6) subsections up to the next H2."""
    from mdview.selection import section_source

    async def driver(app, doc) -> None:
        heading = _heading(doc, "見出しの階層")
        src = section_source(heading, doc)
        assert "### H3 ヘッダ" in src
        assert "###### H6 ヘッダ" in src
        # bounded by the next H2
        assert "## リスト" not in src

    _run(driver)


def test_build_scopes_subheading_expands_through_parent_sections() -> None:
    """A subheading grows through its own section, then the enclosing section."""

    async def driver(app, doc) -> None:
        h3 = _heading(doc, "H3 ヘッダ")
        scopes = build_scopes(h3, doc)
        texts = [_selected_text(app.screen, roots) for roots in scopes]

        # its own section: H3 plus its sub-subsections, not the parent H2 heading
        assert any(
            "H3 ヘッダ" in t and "H6 ヘッダ" in t and "見出しの階層" not in t for t in texts
        )
        # the enclosing H2 section: includes 見出しの階層, but is still bounded
        # (does not leak into neighbouring sections or the whole document)
        assert any(
            "見出しの階層" in t
            and "H6 ヘッダ" in t
            and "リスト" not in t
            and "mdview サンプル" not in t
            for t in texts
        )
        # the document is reached only as the final rung
        assert "mdview サンプル" in texts[-1] and "これでサンプルは終わり" in texts[-1]
        for smaller, larger in zip(texts, texts[1:]):
            assert len(larger) > len(smaller), (smaller, larger)

    _run(driver)
