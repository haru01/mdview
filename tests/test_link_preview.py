"""Mouse-hover preview for ordinary `[text](target)` Markdown links."""

from __future__ import annotations

import asyncio
import types

from mdview.app import MdViewerApp, _LinkHoverPopup
from mdview.linkpreview import (
    is_external_href,
    markdown_link_href,
    section_preview,
    slugify,
)

_DOC = """# Index

Read [the note](note.md), [a section](note.md#second-part), [top](#index),
[the site](https://example.com) and [nothing](missing.md) or [x](image.png).
"""

_NOTE = """---
title: Note
---

# Note

本文テキスト。

## Second part

セクション本文。

## Third part

別のセクション。
"""


def _tree(tmp_path):
    (tmp_path / "index.md").write_text(_DOC, encoding="utf-8")
    (tmp_path / "note.md").write_text(_NOTE, encoding="utf-8")
    return tmp_path / "index.md"


# --- markdown_link_href (pure) ---------------------------------------------


def test_link_href_basic():
    assert markdown_link_href("link('note.md')") == "note.md"


def test_link_href_double_quoted_literal():
    # Textual builds the action with `!r`, so an href containing a quote flips
    # the literal's quoting.
    assert markdown_link_href("link(\"it's.md\")") == "it's.md"


def test_link_href_ignores_wikilink_action():
    """`app.wikilink('x','')` *contains* `link(` — the match must be anchored."""
    assert markdown_link_href("app.wikilink('x','')") is None
    assert markdown_link_href("app.tag_files('x')") is None
    assert markdown_link_href(None) is None
    assert markdown_link_href("") is None
    assert markdown_link_href("link(not_a_literal)") is None


def test_is_external_href():
    assert is_external_href("https://example.com")
    assert is_external_href("mailto:a@b.c")
    assert not is_external_href("note.md")
    assert not is_external_href("../dir/note.md#sec")


# --- section_preview (pure) -------------------------------------------------


def test_slugify_matches_both_spellings():
    assert slugify("My Heading!") == "my-heading"
    assert slugify("#my-heading") == "my-heading"


def test_section_preview_slices_to_next_same_level_heading():
    section = section_preview(_NOTE, "second-part")
    assert section is not None
    assert section.startswith("## Second part")
    assert "セクション本文。" in section
    assert "Third part" not in section


def test_section_preview_top_level_keeps_subsections():
    section = section_preview("# A\n\nx\n\n## B\n\ny\n\n# C\n\nz\n", "a")
    assert section == "# A\n\nx\n\n## B\n\ny"


def test_section_preview_ignores_headings_in_code_fences():
    body = "```\n# Fake\n```\n\n# Real\n\nbody\n"
    assert section_preview(body, "fake") is None
    assert section_preview(body, "real").startswith("# Real")


def test_section_preview_disambiguates_repeats():
    body = "## Notes\n\nfirst\n\n## Notes\n\nsecond\n"
    assert "first" in section_preview(body, "notes")
    assert "second" in section_preview(body, "notes-1")


def test_section_preview_none_when_missing():
    assert section_preview(_NOTE, "nope") is None
    assert section_preview(_NOTE, "") is None


# --- hover behaviour --------------------------------------------------------


def _fake_move(action: str | None):
    """A stand-in MouseMove: on_mouse_move only reads event.style.meta."""
    meta = {"@click": action} if action is not None else {}
    return types.SimpleNamespace(style=types.SimpleNamespace(meta=meta))


def _run(doc, check):
    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await check(app, pilot)

    asyncio.run(driver())


def test_hover_over_md_link_previews_file(tmp_path):
    doc = _tree(tmp_path)

    async def check(app, pilot):
        popup = app.query_one("#link-hover", _LinkHoverPopup)
        app.on_mouse_move(_fake_move("link('note.md')"))
        await pilot.pause()
        assert popup.display is True
        plain = popup.content.plain
        assert "本文テキスト。" in plain
        assert "title:" not in plain  # frontmatter stripped, as for a wikilink

        app.on_mouse_move(_fake_move(None))  # moved off the link
        await pilot.pause()
        assert popup.display is False

    _run(doc, check)


def test_hover_over_md_link_with_anchor_previews_section(tmp_path):
    doc = _tree(tmp_path)

    async def check(app, pilot):
        popup = app.query_one("#link-hover", _LinkHoverPopup)
        app.on_mouse_move(_fake_move("link('note.md#second-part')"))
        await pilot.pause()
        assert popup.display is True
        plain = popup.content.plain
        assert "Second part" in plain
        assert "Third part" not in plain

    _run(doc, check)


def test_hover_over_percent_encoded_anchor(tmp_path):
    """markdown-it percent-encodes a non-ASCII anchor, so the href the span
    carries is `note.md#%E3%82%84…` — it must still find the heading."""
    (tmp_path / "index.md").write_text("# Index\n", encoding="utf-8")
    (tmp_path / "note.md").write_text(
        "# Note\n\nintro\n\n## 詳細\n\n詳細の中身。\n", encoding="utf-8"
    )

    async def check(app, pilot):
        popup = app.query_one("#link-hover", _LinkHoverPopup)
        app.on_mouse_move(_fake_move("link('note.md#%E8%A9%B3%E7%B4%B0')"))
        await pilot.pause()
        assert popup.display is True
        plain = popup.content.plain
        assert "詳細の中身。" in plain
        assert "intro" not in plain

    _run(tmp_path / "index.md", check)


def test_hover_over_in_document_anchor_previews_own_section(tmp_path):
    doc = _tree(tmp_path)

    async def check(app, pilot):
        popup = app.query_one("#link-hover", _LinkHoverPopup)
        app.on_mouse_move(_fake_move("link('#index')"))
        await pilot.pause()
        assert popup.display is True
        assert "Index" in popup.content.plain

    _run(doc, check)


def test_hover_over_external_link_shows_url(tmp_path):
    doc = _tree(tmp_path)

    async def check(app, pilot):
        popup = app.query_one("#link-hover", _LinkHoverPopup)
        app.on_mouse_move(_fake_move("link('https://example.com')"))
        await pilot.pause()
        assert popup.display is True
        assert "https://example.com" in popup.content.plain

    _run(doc, check)


def test_hover_over_missing_or_non_markdown_link_shows_nothing(tmp_path):
    doc = _tree(tmp_path)

    async def check(app, pilot):
        popup = app.query_one("#link-hover", _LinkHoverPopup)
        for href in ("missing.md", "image.png", "#"):
            app.on_mouse_move(_fake_move(f"link({href!r})"))
            await pilot.pause()
            assert popup.display is False, href

    _run(doc, check)


def test_hover_preview_cache_cleared_on_navigation(tmp_path):
    """A preview is cached per document, so a navigated-away document can't leak
    a stale peek (the cache key is the href, which is relative)."""
    doc = _tree(tmp_path)

    async def check(app, pilot):
        app.on_mouse_move(_fake_move("link('note.md')"))
        await pilot.pause()
        assert app._hover_preview_cache
        await app._load_file(tmp_path / "note.md")
        await pilot.pause()
        assert app._hover_preview_cache == {}
        assert app._hover_key is None

    _run(doc, check)
