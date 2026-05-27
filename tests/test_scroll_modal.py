"""ScrollableModalScreen: movement keys scroll the modal's own region.

Covers the base class directly (a synthetic modal) so the Help/Ask AI screens
that subclass it inherit verified behaviour — including the subtlety that a
focused single-line Input swallows the printable letters as text, so arrows /
PageUp / PageDown are what scroll while typing.
"""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer, VerticalScroll
from textual.widgets import Input, Static

from mdview.scroll_modal import ScrollableModalScreen


class _Modal(ScrollableModalScreen):
    def compose(self) -> ComposeResult:
        yield Input(id="q")
        with VerticalScroll(id="body"):
            yield Static("line\n" * 300)

    def scroll_region(self) -> ScrollableContainer:
        return self.query_one("#body", VerticalScroll)


class _Harness(App):
    def on_mount(self) -> None:
        self.push_screen(_Modal())


def _body(app: App) -> VerticalScroll:
    return app.screen.query_one("#body", VerticalScroll)


def test_movement_keys_scroll_the_region() -> None:
    async def driver() -> None:
        app = _Harness()
        async with app.run_test(size=(40, 12)) as pilot:
            await pilot.pause()
            app.screen.set_focus(None)  # nothing focused → letters scroll
            body = _body(app)
            assert body.max_scroll_y > 0, "content must overflow for the test"
            await pilot.press("j")
            await pilot.pause()
            assert body.scroll_y > 0, "`j` scrolls down"
            await pilot.press("G")
            await pilot.pause()
            assert body.scroll_y == body.max_scroll_y, "`G` jumps to the bottom"
            await pilot.press("g")
            await pilot.pause()
            assert body.scroll_y == 0, "`g` jumps back to the top"
            await pilot.press("space")
            await pilot.pause()
            paged = body.scroll_y
            assert paged > 0, "Space pages down"
            await pilot.press("shift+space")
            await pilot.pause()
            assert body.scroll_y < paged, "Shift+Space pages up"

    asyncio.run(driver())


def test_focused_input_types_letters_but_arrows_still_scroll() -> None:
    async def driver() -> None:
        app = _Harness()
        async with app.run_test(size=(40, 12)) as pilot:
            await pilot.pause()
            box = app.screen.query_one("#q", Input)
            box.focus()
            await pilot.pause()
            body = _body(app)
            # A letter key is consumed by the focused Input as text, not a scroll.
            await pilot.press("j")
            await pilot.pause()
            assert box.value == "j", "letters type into the focused input"
            assert body.scroll_y == 0, "letters do not scroll while typing"
            # Arrows / PageDown are ignored by the Input and scroll the region.
            await pilot.press("pagedown")
            await pilot.pause()
            assert body.scroll_y > 0, "PageDown scrolls even with the input focused"

    asyncio.run(driver())
