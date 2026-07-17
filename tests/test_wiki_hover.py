"""Mouse-hover preview for `[[wikilinks]]` (added on top of the wiki feature)."""

from __future__ import annotations

import asyncio
import types
from pathlib import Path

from textual.widgets import MarkdownViewer

from mdview.app import MdViewerApp, _WikiHoverPopup
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
            popup = app.query_one("#wiki-hover", _WikiHoverPopup)
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
            popup = app.query_one("#wiki-hover", _WikiHoverPopup)
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
            popup = app.query_one("#wiki-hover", _WikiHoverPopup)
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
