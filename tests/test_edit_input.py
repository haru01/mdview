from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import Input

import mdview.edit_input as edit_input_mod
from mdview.ai import AiQueryError
from mdview.edit_input import EditInstructionScreen


class _Host(App):
    def __init__(self) -> None:
        super().__init__()
        self.result: object = "unset"

    def on_mount(self) -> None:
        self.push_screen(
            EditInstructionScreen("## A\nold body\n", claude="claude", cwd=Path(".")),
            callback=lambda r: setattr(self, "result", r),
        )


def test_submit_runs_edit_and_dismisses_with_edited_text(monkeypatch) -> None:
    captured = {}

    async def fake_edit(scope, instruction, *, claude, cwd, timeout=120.0):
        captured["scope"] = scope
        captured["instruction"] = instruction
        return "## A\nnew body"

    monkeypatch.setattr(edit_input_mod, "edit_markdown", fake_edit)

    async def driver() -> None:
        app = _Host()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.screen.query_one("#edit-input-field", Input).value = "書き換えて"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.result == "## A\nnew body"
            assert captured["instruction"] == "書き換えて"
            assert captured["scope"] == "## A\nold body\n"

    asyncio.run(driver())


def test_error_keeps_dialog_open(monkeypatch) -> None:
    async def fake_edit(*args, **kwargs):
        raise AiQueryError("boom")

    monkeypatch.setattr(edit_input_mod, "edit_markdown", fake_edit)

    async def driver() -> None:
        app = _Host()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            app.screen.query_one("#edit-input-field", Input).value = "x"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            # Still on the instruction screen; no edit was produced.
            assert isinstance(app.screen, EditInstructionScreen)
            assert app.result == "unset"

    asyncio.run(driver())


def test_escape_dismisses_with_none() -> None:
    async def driver() -> None:
        app = _Host()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            assert app.result is None

    asyncio.run(driver())
