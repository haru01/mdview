"""Modal that shows Claude's SVG-illustrated explanation of a `##` section.

The read-only counterpart to `ask_ai.py`: there is no question box here (the
prompt is fixed and was already run in the background when the reader clicked the
heading's lightbulb). It just displays the generated diagram(s) above the prose,
re-rendered with a bare `Markdown` widget so it inherits the main view's colours
and line spacing (theme.css styles `Markdown`/`MarkdownBlock` by type).
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer, VerticalScroll
from textual.widgets import Markdown

from mdview.scroll_modal import ScrollableModalScreen
from mdview.svg_widgets import render_svgs_into


class SectionInsightScreen(ScrollableModalScreen):
    # Scrollable via the inherited movement keys (j/k, d/u, f/b, Space, g/G).
    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    def __init__(self, prose: str, svgs: list[str], *, tmpdir: Path) -> None:
        super().__init__()
        self._prose = prose
        self._svgs = svgs
        self._tmpdir = tmpdir

    def compose(self) -> ComposeResult:
        with Container(id="section-insight-dialog") as dialog:
            dialog.border_title = "セクション解説"
            with VerticalScroll(id="section-insight-body"):
                yield Markdown(self._prose, id="section-insight-prose")

    async def on_mount(self) -> None:
        # Mount the diagram(s) ahead of the prose so the figure leads. Done in
        # on_mount (not compose) so the dialog's width is known for sizing.
        scroll = self.query_one("#section-insight-body", VerticalScroll)
        prose = self.query_one("#section-insight-prose", Markdown)
        await render_svgs_into(
            scroll,
            self._svgs,
            self._tmpdir,
            width_hint=max(400, (self.size.width or 80) * 12),
            before=prose,
            prefix="section-insight",
        )

    def scroll_region(self) -> ScrollableContainer:
        return self.query_one("#section-insight-body", VerticalScroll)

    def action_dismiss(self) -> None:
        self.dismiss()
