"""App-level wiring for Obsidian-style `[[wikilink]]` navigation (P1)."""

from __future__ import annotations

import asyncio
import types
from pathlib import Path

from textual.widgets import Markdown, MarkdownViewer

from mdview.app import MdViewerApp, _WikiHoverPopup

FIXTURES = Path(__file__).parent / "fixtures"


def test_wikilink_is_rewritten_in_rendered_source() -> None:
    """`[[wiki_b]]` becomes a `wikilink:` link; code fences stay literal."""

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            source = app.query_one(MarkdownViewer).document.source
            assert "[wiki_b](wikilink:wiki_b)" in source
            assert "[別名で表示](wikilink:wiki_b)" in source
            # inside the fence and inline code, the literal must survive
            assert "[[wiki_b]] is inside a fence" in source
            assert "`[[wiki_b]]`" in source

    asyncio.run(driver())


def test_frontmatter_renders_readably_with_clickable_wikilink() -> None:
    """A file's YAML frontmatter renders one key per line, and a `[[wikilink]]`
    in a value becomes a clickable link (not a collapsed setext heading)."""

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_fm_doc.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            source = app.query_one(MarkdownViewer).document.source
            # one key per line (blockquote list), not a one-line setext heading
            assert "> - **title**: Doc" in source
            assert ">   - spec" in source  # nested list item, indented
            # wikilink inside frontmatter is now a clickable link
            assert "[wiki_b](wikilink:wiki_b)" in source
            # the raw `---` fence is gone (no leading setext-heading mangling)
            assert not source.startswith("---")

    asyncio.run(driver())


def test_frontmatter_wikilink_click_navigates() -> None:
    """Clicking a wikilink that lived in the frontmatter navigates."""

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_fm_doc.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            doc = app.query_one(MarkdownViewer).document
            doc.post_message(Markdown.LinkClicked(doc, "wikilink:wiki_b"))
            for _ in range(20):
                await pilot.pause()
                if app._md_path.name == "wiki_b.md":
                    break
            assert app._md_path.name == "wiki_b.md"

    asyncio.run(driver())


def test_wikilink_click_navigates_to_note() -> None:
    """Clicking a `wikilink:` link loads the resolved note."""

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app._md_path.name == "wiki_a.md"
            doc = app.query_one(MarkdownViewer).document
            # LinkClicked delivers the href already URL-decoded.
            doc.post_message(Markdown.LinkClicked(doc, "wikilink:wiki_b"))
            for _ in range(20):
                await pilot.pause()
                if app._md_path.name == "wiki_b.md":
                    break
            assert app._md_path.name == "wiki_b.md"

    asyncio.run(driver())


def test_peek_picker_lists_wikilinks_then_previews_and_jumps() -> None:
    """`p` opens the picker; choosing a link previews it, `o` jumps to it."""
    from mdview.wiki_peek import WikiLinkPickerScreen, WikiPeekScreen

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert isinstance(app.screen, WikiLinkPickerScreen)
            # two unique targets (wiki_b deduped across plain + alias), does_not_exist
            assert [t for t, _ in app.screen._ranked] == ["wiki_b", "does_not_exist"]

            await pilot.press("enter")  # pick the highlighted first row (wiki_b)
            for _ in range(20):
                await pilot.pause()
                if isinstance(app.screen, WikiPeekScreen):
                    break
            assert isinstance(app.screen, WikiPeekScreen)
            assert app._md_path.name == "wiki_a.md"  # preview does not navigate

            await pilot.press("o")  # jump to the previewed note
            for _ in range(20):
                await pilot.pause()
                if app._md_path.name == "wiki_b.md":
                    break
            assert app._md_path.name == "wiki_b.md"

    asyncio.run(driver())


def test_peek_preview_close_does_not_navigate() -> None:
    """Esc in the preview closes it without navigating."""
    from mdview.wiki_peek import WikiPeekScreen

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
                if isinstance(app.screen, WikiPeekScreen):
                    break
            await pilot.press("escape")
            for _ in range(10):
                await pilot.pause()
            assert app._md_path.name == "wiki_a.md"

    asyncio.run(driver())


def test_peek_with_no_wikilinks_notifies() -> None:
    """`p` on a doc with no wikilinks shows a notice, opens no picker."""
    from mdview.wiki_peek import WikiLinkPickerScreen

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "link_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
            assert not isinstance(app.screen, WikiLinkPickerScreen)

    asyncio.run(driver())


def test_wikilink_resolves_vault_wide_across_folders(tmp_path) -> None:
    """The real Obsidian flow: `mdview <vault>` resolves `[[note]]` by name
    anywhere under the vault root, even in a different folder than the current
    file (exercises the `_root_dir` branch of `_resolve_wikilink`)."""
    notes = tmp_path / "notes"
    refs = tmp_path / "refs"
    notes.mkdir()
    refs.mkdir()
    (notes / "a.md").write_text("# A\n\nSee [[SELF-H-001]].\n", encoding="utf-8")
    (refs / "SELF-H-001.md").write_text("# H-001\n\nspec.\n", encoding="utf-8")

    async def driver() -> None:
        app = MdViewerApp(notes / "a.md", root_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            doc = app.query_one(MarkdownViewer).document
            doc.post_message(Markdown.LinkClicked(doc, "wikilink:SELF-H-001"))
            for _ in range(20):
                await pilot.pause()
                if app._md_path.name == "SELF-H-001.md":
                    break
            assert app._md_path == refs / "SELF-H-001.md"

    asyncio.run(driver())


def _fake_move(action: str | None):
    """A stand-in MouseMove: on_mouse_move only reads event.style.meta."""
    meta = {"@click": action} if action is not None else {}
    return types.SimpleNamespace(style=types.SimpleNamespace(meta=meta))


def test_hover_over_wikilink_shows_popup_and_leaving_hides_it() -> None:
    """Hovering a `[[wikilink]]` shows the preview; moving off hides it."""

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            popup = app.query_one("#wiki-hover", _WikiHoverPopup)
            assert popup.display is False

            app.on_mouse_move(_fake_move("link('wikilink:wiki_b')"))
            await pilot.pause()
            assert popup.display is True  # preview shown

            app.on_mouse_move(_fake_move(None))  # moved off the link
            await pilot.pause()
            assert popup.display is False  # hidden again

    asyncio.run(driver())


def test_real_mouse_move_reaches_app_with_style() -> None:
    """Plumbing probe: a real MouseMove (not a fake) bubbles to App.on_mouse_move
    with its style populated — the pipeline the hover feature depends on.

    (Whether the popup then *renders* at the cursor is a visual check left to a
    real terminal; this only proves the event/style plumbing.)"""

    import mdview.app as app_module

    captured: list[object] = []

    class _SpyApp(MdViewerApp):
        # Subclassing moves CSS_PATH resolution to this test module's dir; pin it
        # back to the real stylesheet next to app.py.
        CSS_PATH = str(Path(app_module.__file__).parent / "theme.css")

        def on_mouse_move(self, event):  # noqa: ANN001, D401
            captured.append(getattr(event, "style", None))
            return super().on_mouse_move(event)

    async def driver() -> None:
        app = _SpyApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.hover(MarkdownViewer, offset=(5, 3))
            await pilot.pause()
            assert captured, "MouseMove never reached App.on_mouse_move"
            assert any(s is not None for s in captured), "style not populated"

    asyncio.run(driver())


def test_hover_over_non_wikilink_does_not_show_popup() -> None:
    """A normal `[..](x.md)` link (or plain text) shows no hover preview."""

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            popup = app.query_one("#wiki-hover", _WikiHoverPopup)
            app.on_mouse_move(_fake_move("link('other.md')"))
            await pilot.pause()
            assert popup.display is False

    asyncio.run(driver())


def test_hover_preview_strips_yaml_frontmatter() -> None:
    """The hover preview omits a note's leading YAML metadata block."""

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            preview = app._wiki_preview_text("wiki_meta")
            assert preview is not None
            assert "title:" not in preview
            assert "tags:" not in preview
            assert preview.startswith("# Meta Note")

    asyncio.run(driver())


def test_hover_over_missing_wikilink_shows_no_popup() -> None:
    """Hovering a wikilink that resolves to nothing shows nothing."""

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            popup = app.query_one("#wiki-hover", _WikiHoverPopup)
            app.on_mouse_move(_fake_move("link('wikilink:does_not_exist')"))
            await pilot.pause()
            assert popup.display is False

    asyncio.run(driver())


def test_missing_wikilink_notifies_and_stays_put() -> None:
    """A wikilink with no matching file surfaces a notice, no navigation."""

    async def driver() -> None:
        app = MdViewerApp(FIXTURES / "wiki_a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            doc = app.query_one(MarkdownViewer).document
            doc.post_message(Markdown.LinkClicked(doc, "wikilink:does_not_exist"))
            for _ in range(20):
                await pilot.pause()
            assert app._md_path.name == "wiki_a.md"

    asyncio.run(driver())
