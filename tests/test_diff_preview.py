from __future__ import annotations

import asyncio

from textual.app import App
from textual.widgets import Static

from mdview.diff_preview import DiffPreviewScreen


class _Host(App):
    def __init__(self, original: str, edited: str) -> None:
        super().__init__()
        self._original = original
        self._edited = edited
        self.result: object = "unset"

    def on_mount(self) -> None:
        self.push_screen(
            DiffPreviewScreen(self._original, self._edited, label="A"),
            callback=lambda r: setattr(self, "result", r),
        )


def _run(original: str, edited: str, keys: list[str]) -> object:
    async def driver() -> object:
        app = _Host(original, edited)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, DiffPreviewScreen)
            # _render_preview ran in compose without error and shows content.
            assert app.screen.query_one("#diff-preview-content", Static)
            for key in keys:
                await pilot.press(key)
            await pilot.pause()
            return app.result

    return asyncio.run(driver())


def test_accept_with_y_returns_true() -> None:
    assert _run("## A\nold\n", "## A\nnew\n", ["y"]) is True


def test_reject_with_n_returns_false() -> None:
    assert _run("## A\nold\n", "## A\nnew\n", ["n"]) is False


def test_reject_with_escape_returns_false() -> None:
    assert _run("## A\nold\n", "## A\nnew\n", ["escape"]) is False
