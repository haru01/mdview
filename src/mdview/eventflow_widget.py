"""Textual wrapper that renders one EventStorming flow as sticky-note swimlanes.

Thin by design (the rendering lives in the pure `mdview.eventflowview`): an
`EventFlow` container holds a `Static` of the colour-coded box-art `Text`. The
container scrolls horizontally (theme.css `overflow-x: auto`) so a flow wider than
the screen is drawn at natural width and scrolled rather than wrapped — hence a
scroll container with a `width: auto` child (a plain `Static` clamps its content
to the viewport and never overflows).

Selection is overridden so the *displayed* text (box-drawing characters) and the
*selectable* text differ: selecting a flow (for copy or Ask AI) yields the
original `event-flow-svg` DSL, which reads well as a prompt. This mirrors
`DiffHunk`, whose selection returns a clean unified diff rather than its gutter.
Because `MdViewerApp._apply_scope` selects the widget *and all its descendants*,
the inner `Static` must not contribute its box-art — so its `get_selection`
returns ``None`` and only the container yields the DSL.

It lives in its own module so `mdview.selection` can treat `EventFlow` as an
atomic block without importing `mdview.app` (which would be circular) — the same
arrangement as `DiffHunk`.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.selection import Selection
from textual.widgets import Static

from mdview.eventflow import Flow
from mdview.eventflowview import render_flow


class _FlowBody(Static):
    """The box-art itself; never contributes to a text selection (the parent
    `EventFlow` yields the clean DSL instead)."""

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        return None


class EventFlow(ScrollableContainer):
    """A colour-coded, horizontally scrollable rendering of one event flow."""

    def __init__(self, flow: Flow, *, source: str) -> None:
        self._flow = flow
        self._source = source  # the original DSL (selectable / Ask-AI text)
        super().__init__()

    def compose(self) -> ComposeResult:
        # width:auto (theme.css) so the body keeps its natural width and the
        # container scrolls horizontally when it exceeds the viewport.
        yield _FlowBody(render_flow(self._flow))

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        # Extract from the clean DSL, not the box-art display. For a whole-widget
        # selection (SELECT_ALL) this returns the entire fence source.
        return selection.extract(self._source), "\n"

    def render_text(self) -> Text:
        """The displayed box-art as a Rich `Text` (for search re-highlighting)."""
        return render_flow(self._flow)
