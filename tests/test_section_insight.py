from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from textual.app import App
from textual.widgets import Markdown

from mdview.image_zoom import ZoomableImage
from mdview.section_insight import SectionInsightScreen

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="30">'
    '<rect width="80" height="30" fill="#4ebf71"/></svg>'
)


class _Host(App):
    def __init__(self, prose: str, svgs: list[str], tmpdir: Path) -> None:
        super().__init__()
        self._prose = prose
        self._svgs = svgs
        self._tmpdir = tmpdir

    def on_mount(self) -> None:
        self.push_screen(SectionInsightScreen(self._prose, self._svgs, tmpdir=self._tmpdir))


def test_section_insight_screen_shows_prose_and_svg() -> None:
    """The modal renders the explanation prose as Markdown and any SVG as a
    click-to-zoom image."""

    async def driver() -> None:
        with tempfile.TemporaryDirectory() as td:
            app = _Host("これは**解説**です。", [_SVG], Path(td))
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await pilot.pause()
                assert isinstance(app.screen, SectionInsightScreen)
                assert app.screen.query_one("#section-insight-prose", Markdown)
                images = list(app.screen.query(ZoomableImage))
                assert images, "the SVG should render as a ZoomableImage"

    asyncio.run(driver())


def test_section_insight_screen_dismisses_on_q() -> None:
    """`q` (and Esc) close the modal without quitting the app."""

    async def driver() -> None:
        with tempfile.TemporaryDirectory() as td:
            app = _Host("text", [], Path(td))
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                await pilot.pause()
                assert isinstance(app.screen, SectionInsightScreen)
                await pilot.press("q")
                await pilot.pause()
                assert not isinstance(app.screen, SectionInsightScreen)

    asyncio.run(driver())
