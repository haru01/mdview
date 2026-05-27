"""App-level pilot tests for the AI edit loop (select text → `w` → diff preview)."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

import pytest
from textual.widgets import MarkdownViewer

from mdview.app import MdViewerApp

_DOC = "# Doc Title\n\n## Alpha\n\nalpha body line.\n\n## Beta\n\nbeta body line.\n"


async def _coro(value: str) -> str:
    """Wrap a value as an awaitable (for monkeypatching the async edit_markdown)."""
    return value


def _write_doc(tmp_path: Path, text: str = _DOC) -> Path:
    md = tmp_path / "doc.md"
    md.write_text(text, encoding="utf-8")
    return md


def _patch_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `find_claude` report a binary so editing is enabled (and 💡 injected)."""
    monkeypatch.setattr("mdview.app.find_claude", lambda: "claude")


def _select_block(app: MdViewerApp, block_text: str) -> None:
    """Select the paragraph containing *block_text* as a whole block (SELECT_ALL)."""
    from textual.selection import SELECT_ALL
    from textual.widgets._markdown import MarkdownParagraph

    para = next(
        p for p in app.query(MarkdownParagraph) if block_text in str(p._render())
    )
    app.screen.selections = {para: SELECT_ALL}


async def _apply_selection_edit(
    app: MdViewerApp, pilot, block_text: str, *, accept: str = "y"
) -> None:
    """Select a block, press `w`, fill the instruction, and accept/reject the diff."""
    from textual.widgets import Input

    _select_block(app, block_text)
    app.action_edit_selection()  # = the `w` binding
    await pilot.pause()
    app.screen.query_one("#edit-input-field", Input).value = "go"
    await pilot.press("enter")
    await app.workers.wait_for_complete()
    await pilot.pause()
    await pilot.press(accept)
    await app.workers.wait_for_complete()
    await pilot.pause()


def test_selection_edit_happy_path_sends_only_selection_and_applies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_claude(monkeypatch)
    captured: dict[str, str] = {}

    async def fake_edit(scope, instruction, *, claude, cwd, timeout=120.0):
        captured["scope"] = scope
        return "alpha REWRITTEN."

    monkeypatch.setattr("mdview.edit_input.edit_markdown", fake_edit)
    md = _write_doc(tmp_path)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _apply_selection_edit(app, pilot, "alpha body line.")
            source = app.query_one(MarkdownViewer).document.source
            # Only the selected block was sent to the LLM (no document context).
            assert "alpha body line." in captured["scope"]
            assert "beta body line." not in captured["scope"]
            assert "# Doc Title" not in captured["scope"]
            # ...and only the selection changed.
            assert "alpha REWRITTEN." in source
            assert "alpha body line." not in source
            assert "beta body line." in source
            assert "## Alpha" in source and "## Beta" in source
            assert len(app._undo_stack) == 1
            assert source != app._disk_baseline  # dirty

    asyncio.run(driver())


def test_selection_edit_reject_leaves_buffer_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_claude(monkeypatch)
    monkeypatch.setattr(
        "mdview.edit_input.edit_markdown", lambda *a, **k: _coro("alpha REWRITTEN.")
    )
    md = _write_doc(tmp_path)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            before = app.query_one(MarkdownViewer).document.source
            await _apply_selection_edit(app, pilot, "alpha body line.", accept="n")
            after = app.query_one(MarkdownViewer).document.source
            assert after == before
            assert app._undo_stack == []
            assert not app._is_dirty()

    asyncio.run(driver())


def test_selection_edit_noop_when_output_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_claude(monkeypatch)

    async def echo(scope, instruction, *, claude, cwd, timeout=120.0):
        return scope.rstrip("\n")  # identical content (edit_markdown strips)

    monkeypatch.setattr("mdview.edit_input.edit_markdown", echo)
    md = _write_doc(tmp_path)

    async def driver() -> None:
        from textual.widgets import Input

        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            _select_block(app, "alpha body line.")
            app.action_edit_selection()
            await pilot.pause()
            app.screen.query_one("#edit-input-field", Input).value = "そのまま"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            # No diff preview for a no-op edit; we're back on the main screen.
            from mdview.diff_preview import DiffPreviewScreen

            assert not isinstance(app.screen, DiffPreviewScreen)
            assert app._undo_stack == []
            assert "alpha body line." in app.query_one(MarkdownViewer).document.source

    asyncio.run(driver())


def test_headings_show_lightbulb_but_no_pencil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_claude(monkeypatch)
    md = _write_doc(tmp_path)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app._insight_headings, "lightbulb markers should be injected"
            for heading in app._insight_headings.values():
                shown = heading._content.plain
                assert "💡" in shown, "the insight lightbulb stays"
                assert "✏️" not in shown, "the edit pencil is gone"

    asyncio.run(driver())


def test_undo_reverts_applied_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_claude(monkeypatch)
    monkeypatch.setattr(
        "mdview.edit_input.edit_markdown", lambda *a, **k: _coro("alpha EDITED.")
    )
    md = _write_doc(tmp_path)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _apply_selection_edit(app, pilot, "alpha body line.")
            assert "alpha EDITED." in app.query_one(MarkdownViewer).document.source
            app._run_command("undo")
            await app.workers.wait_for_complete()
            await pilot.pause()
            source = app.query_one(MarkdownViewer).document.source
            assert "alpha EDITED." not in source
            assert "alpha body line." in source
            assert app._undo_stack == []
            assert not app._is_dirty()

    asyncio.run(driver())


def test_quit_guard_blocks_then_force_quit_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_claude(monkeypatch)
    monkeypatch.setattr(
        "mdview.edit_input.edit_markdown", lambda *a, **k: _coro("alpha EDITED.")
    )
    md = _write_doc(tmp_path)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _apply_selection_edit(app, pilot, "alpha body line.")
            assert app._is_dirty()
            exits: list = []
            monkeypatch.setattr(app, "exit", lambda *a, **k: exits.append(True))
            await pilot.press("q")  # guarded: must NOT exit while dirty
            await pilot.pause()
            assert exits == []
            app._run_command("q!")  # force quit
            assert exits == [True]

    asyncio.run(driver())


def test_write_saves_to_disk_and_clears_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_claude(monkeypatch)
    monkeypatch.setattr(
        "mdview.edit_input.edit_markdown", lambda *a, **k: _coro("alpha EDITED.")
    )
    md = _write_doc(tmp_path)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _apply_selection_edit(app, pilot, "alpha body line.")
            assert app._is_dirty()
            app._run_command("w")
            buffer = app.query_one(MarkdownViewer).document.source
            assert md.read_text(encoding="utf-8") == buffer
            assert "alpha EDITED." in md.read_text(encoding="utf-8")
            assert not app._is_dirty()
            exits: list = []
            monkeypatch.setattr(app, "exit", lambda *a, **k: exits.append(True))
            await pilot.press("q")  # clean buffer quits without the guard
            await pilot.pause()
            assert exits == [True]

    asyncio.run(driver())


def test_write_refuses_stdin_document() -> None:
    async def driver() -> None:
        app = MdViewerApp(content="# stdin\n\n## A\nbody\n")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app._write_file() is False

    asyncio.run(driver())


def test_edit_selection_refuses_partial_drag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_claude(monkeypatch)
    md = _write_doc(tmp_path)

    async def driver() -> None:
        from textual.geometry import Offset
        from textual.selection import Selection
        from textual.widgets._markdown import MarkdownParagraph

        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            para = next(
                p
                for p in app.query(MarkdownParagraph)
                if "alpha body line." in str(p._render())
            )
            # A partial (freeform-drag) selection, not SELECT_ALL.
            app.screen.selections = {para: Selection(Offset(0, 0), Offset(3, 0))}
            app.action_edit_selection()
            await pilot.pause()
            from mdview.edit_input import EditInstructionScreen

            assert not isinstance(app.screen, EditInstructionScreen)

    asyncio.run(driver())


def test_edit_selection_without_selection_notifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_claude(monkeypatch)
    md = _write_doc(tmp_path)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.screen.selections = {}
            app.action_edit_selection()
            await pilot.pause()
            from mdview.edit_input import EditInstructionScreen

            assert not isinstance(app.screen, EditInstructionScreen)

    asyncio.run(driver())


def test_selection_edit_end_to_end_strips_fence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full chain through the real `edit_markdown`: a fenced reply is unwrapped."""
    from tests.test_ai import _fake_claude_multiline

    claude = _fake_claude_multiline(tmp_path, stdout="```markdown\nFENCED EDIT.\n```")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(claude, bindir / "claude")
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    md = _write_doc(tmp_path)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _apply_selection_edit(app, pilot, "alpha body line.")
            source = app.query_one(MarkdownViewer).document.source
            assert "FENCED EDIT." in source
            assert "```" not in source  # the wrapping fence was stripped

    asyncio.run(driver())
