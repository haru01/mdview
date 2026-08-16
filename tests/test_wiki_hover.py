"""Mouse-hover preview for `[[wikilinks]]` (added on top of the wiki feature)."""

from __future__ import annotations

import asyncio
import types
from pathlib import Path

from textual.widgets import MarkdownViewer

from mdview.app import MdViewerApp, _LinkHoverPopup
from mdview.wiki import wikilink_action_target

_FM_A = "---\ntitle: Note A\ntags: [alpha]\n---\n"
_FM_B = "---\ntitle: Target B\ntags: [x]\n---\n"


def _wiki_tree(tmp_path):
    (tmp_path / "a.md").write_text(
        _FM_A + "\n# Note A\n\nSee [[target-b]] and [[missing-x]] here.\n"
    )
    (tmp_path / "target-b.md").write_text(_FM_B + "\n# Target B\n\n本文テキスト。\n")
    return tmp_path / "a.md"


# --- wikilink_action_target (pure) -----------------------------------------


def test_action_target_basic():
    assert wikilink_action_target("app.wikilink('target-b','')") == "target-b"


def test_action_target_with_anchor_arg():
    assert wikilink_action_target("app.wikilink('note','sec')") == "note"


def test_action_target_unescapes():
    assert wikilink_action_target("app.wikilink('a\\'b','')") == "a'b"


def test_action_target_none_for_other_actions():
    assert wikilink_action_target("app.tag_files('x')") is None
    assert wikilink_action_target("app.section_insight('h')") is None
    assert wikilink_action_target(None) is None
    assert wikilink_action_target("") is None


# --- themed preview render (pure) ------------------------------------------


def test_hover_preview_uses_accent_not_rich_defaults():
    """The hover preview renders through the Obsidian palette, so inline code /
    links come out accent-purple — not Rich Markdown's default cyan/blue."""
    from mdview.app import _render_preview_markdown
    from mdview.palette import ACCENT  # #7f6df2

    accent_rgb = tuple(int(ACCENT[i : i + 2], 16) for i in (1, 3, 5))  # (127,109,242)
    text = _render_preview_markdown("本文 `code` と [link](http://example.com)。")

    triplets = set()
    for span in text.spans:
        color = getattr(span.style, "color", None)
        if color is not None:
            tr = color.get_truecolor()
            triplets.add((tr.red, tr.green, tr.blue))

    # inline code + link both remap to the accent purple.
    assert accent_rgb in triplets, f"accent {accent_rgb} missing from {triplets}"
    # Rich's default inline-code cyan (0,128,128) must not survive the remap.
    assert (0, 128, 128) not in triplets


# --- hover behaviour -------------------------------------------------------


def _fake_move(action: str | None):
    """A stand-in MouseMove: on_mouse_move only reads event.style.meta."""
    meta = {"@click": action} if action is not None else {}
    return types.SimpleNamespace(style=types.SimpleNamespace(meta=meta))


def test_hover_shows_preview_then_hides(tmp_path):
    doc = _wiki_tree(tmp_path)

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            popup = app.query_one("#link-hover", _LinkHoverPopup)
            assert popup.display is False

            app.on_mouse_move(_fake_move("app.wikilink('target-b','')"))
            await pilot.pause()
            assert popup.display is True

            app.on_mouse_move(_fake_move(None))  # moved off the link
            await pilot.pause()
            assert popup.display is False

    asyncio.run(driver())


def test_hover_preview_strips_frontmatter(tmp_path):
    doc = _wiki_tree(tmp_path)

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            preview = app._wiki_preview_text("target-b")
            assert preview is not None
            assert "title:" not in preview
            assert preview.startswith("# Target B")

    asyncio.run(driver())


def test_hover_over_broken_link_shows_nothing(tmp_path):
    doc = _wiki_tree(tmp_path)

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            popup = app.query_one("#link-hover", _LinkHoverPopup)
            app.on_mouse_move(_fake_move("app.wikilink('missing-x','')"))
            await pilot.pause()
            assert popup.display is False

    asyncio.run(driver())


def test_hover_over_non_wikilink_shows_nothing(tmp_path):
    doc = _wiki_tree(tmp_path)

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            popup = app.query_one("#link-hover", _LinkHoverPopup)
            app.on_mouse_move(_fake_move("app.tag_files('alpha')"))
            await pilot.pause()
            assert popup.display is False

    asyncio.run(driver())


def test_real_mouse_move_reaches_app_with_style(tmp_path):
    """Plumbing probe: a real MouseMove bubbles to App.on_mouse_move with its
    style populated — the pipeline the hover feature depends on. (Whether the
    popup then renders at the cursor is a visual check left to a real terminal.)"""
    import mdview.app as app_module

    doc = _wiki_tree(tmp_path)
    captured: list[object] = []

    class _SpyApp(MdViewerApp):
        CSS_PATH = str(Path(app_module.__file__).parent / "theme.css")

        def on_mouse_move(self, event):  # noqa: ANN001
            captured.append(getattr(event, "style", None))
            return super().on_mouse_move(event)

    async def driver():
        app = _SpyApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.hover(MarkdownViewer, offset=(5, 3))
            await pilot.pause()
            assert captured, "MouseMove never reached App.on_mouse_move"
            assert any(s is not None for s in captured), "style not populated"

    asyncio.run(driver())
