from __future__ import annotations

import asyncio

from textual.widgets import MarkdownViewer
from textual.widgets._markdown import MarkdownBlock

from mdview.app import MdViewerApp, _FrontmatterPanel
from mdview.wiki_tag import WikiPickScreen

_FM = "---\ntitle: Note A\ntype: concept\ntags: [alpha, beta]\n---\n"


def _wiki_tree(tmp_path):
    """A small wiki: a.md (frontmatter + a wikilink) plus link targets."""
    (tmp_path / "a.md").write_text(
        _FM + "\n# Note A\n\nSee [[target-b]] and [[missing-x]] here.\n"
    )
    (tmp_path / "target-b.md").write_text("# Target B\n\nbody\n")
    return tmp_path / "a.md"


# --- frontmatter -----------------------------------------------------------


def test_frontmatter_stripped_from_source_and_panel_injected(tmp_path):
    doc = _wiki_tree(tmp_path)

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            assert "title:" not in viewer.document.source
            assert viewer.document.source.lstrip().startswith("# Note A")
            panels = list(app.query(_FrontmatterPanel))
            assert len(panels) == 1
            rendered = panels[0].render().plain
            assert "Note A" in rendered
            assert "alpha" in rendered and "beta" in rendered

    asyncio.run(driver())


def test_write_preserves_frontmatter_round_trip(tmp_path):
    doc = _wiki_tree(tmp_path)
    original = doc.read_text()

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app._write_file() is True
            assert doc.read_text() == original  # frontmatter intact

    asyncio.run(driver())


def test_write_after_body_edit_keeps_frontmatter(tmp_path):
    doc = _wiki_tree(tmp_path)

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await app._render_source("# Edited\n\nnew body\n")
            assert app._is_dirty()
            assert app._write_file() is True
            written = doc.read_text()
            assert written.startswith(_FM)
            assert "# Edited" in written
            assert "Note A" not in written.split("---\n", 2)[-1]

    asyncio.run(driver())


# --- wikilinks -------------------------------------------------------------


def test_wikilink_injected_source_pristine_render_clickable(tmp_path):
    doc = _wiki_tree(tmp_path)

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            # Source keeps the raw wikilink syntax (so editing/saving round-trips).
            assert "[[target-b]]" in viewer.document.source
            # Some block was rewritten: it carries the clean base and its rendered
            # content no longer shows the literal `[[...]]`.
            injected = [
                b for b in app.query(MarkdownBlock) if hasattr(b, "_wikilink_base")
            ]
            assert injected
            block = injected[0]
            assert "[[target-b]]" in block._wikilink_base.plain
            assert "[[target-b]]" not in block._content.plain
            styles = " ".join(str(s.style) for s in block._content.spans)
            assert "app.wikilink" in styles

    asyncio.run(driver())


def test_wikilink_action_navigates_to_target(tmp_path):
    doc = _wiki_tree(tmp_path)

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.action_wikilink("target-b", "")
            for _ in range(20):
                await pilot.pause()
                if app._md_path.name == "target-b.md":
                    break
            assert app._md_path.name == "target-b.md"

    asyncio.run(driver())


def test_wikilink_click_navigates(tmp_path):
    """A real mouse click on the rendered link span routes to the target file."""
    from textual.geometry import Offset
    from textual.widgets._markdown import MarkdownParagraph

    (tmp_path / "a.md").write_text("# A\n\nSee [[target-b]] here.\n")
    (tmp_path / "target-b.md").write_text("# Target B\n")

    async def driver():
        app = MdViewerApp(tmp_path / "a.md")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            para = next(
                p
                for p in app.query(MarkdownParagraph)
                if hasattr(p, "_wikilink_base")
            )
            # rendered "See target-b here." — click inside "target-b" (col ~6)
            await pilot.click(para, offset=Offset(6, 0))
            for _ in range(20):
                await pilot.pause()
                if app._md_path.name == "target-b.md":
                    break
            assert app._md_path.name == "target-b.md"

    asyncio.run(driver())


def test_broken_wikilink_action_does_not_navigate(tmp_path):
    doc = _wiki_tree(tmp_path)

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.action_wikilink("missing-x", "")
            for _ in range(5):
                await pilot.pause()
            assert app._md_path.name == "a.md"  # stayed put

    asyncio.run(driver())


def test_ambiguous_wikilink_opens_picker(tmp_path):
    (tmp_path / "one" / "dup.md").parent.mkdir()
    (tmp_path / "one" / "dup.md").write_text("# one dup\n")
    (tmp_path / "two").mkdir()
    (tmp_path / "two" / "dup.md").write_text("# two dup\n")
    doc = tmp_path / "a.md"
    doc.write_text("# A\n\n[[dup]]\n")

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.action_wikilink("dup", "")
            await pilot.pause()
            assert isinstance(app.screen, WikiPickScreen)
            assert len(app.screen._paths) == 2

    asyncio.run(driver())


# --- tags ------------------------------------------------------------------


def test_tag_action_opens_picker_with_matching_files(tmp_path):
    doc = _wiki_tree(tmp_path)
    (tmp_path / "c.md").write_text(
        "---\ntitle: C\ntags: [alpha]\n---\n\n# C\n"
    )

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.action_tag_files("alpha")
            await pilot.pause()
            assert isinstance(app.screen, WikiPickScreen)
            names = {p.name for p in app.screen._paths}
            assert names == {"a.md", "c.md"}

    asyncio.run(driver())


def test_tag_picker_dismiss_navigates(tmp_path):
    doc = _wiki_tree(tmp_path)  # a.md has tags alpha, beta
    (tmp_path / "d.md").write_text("---\ntitle: D\ntags: [beta]\n---\n\n# D\n")

    async def driver():
        app = MdViewerApp(doc)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.action_tag_files("beta")  # picker over a.md + d.md
            await pilot.pause()
            assert isinstance(app.screen, WikiPickScreen)
            app.screen.dismiss(tmp_path / "d.md")  # routes through action's callback
            for _ in range(20):
                await pilot.pause()
                if app._md_path.name == "d.md":
                    break
            assert app._md_path.name == "d.md"

    asyncio.run(driver())
