from __future__ import annotations

from textual.selection import SELECT_ALL

from mdview.eventflow import parse_flow_dsl
from mdview.eventflow_widget import EventFlow

_DSL = (
    "title: ハッピーパス\n"
    "flow:\n"
    "|community|: 主催者が活動を始める\n"
    "  @主催者 > !コミュニティを作成 > [コミュニティが作成された]\n"
)


def test_get_selection_returns_source_dsl() -> None:
    """Selecting/Ask-AI'ing a flow yields the original DSL, not the box art."""
    flow = parse_flow_dsl(_DSL)
    widget = EventFlow(flow, source=_DSL)
    text, ending = widget.get_selection(SELECT_ALL)
    # Selection.extract drops a single trailing newline; the DSL is otherwise intact.
    assert text == _DSL.rstrip("\n")
    assert ending == "\n"
    # The decorative box-drawing must never leak into the selection.
    assert "┌" not in text
    assert "─>" not in text


def test_render_text_matches_renderer() -> None:
    from mdview.eventflowview import render_flow

    flow = parse_flow_dsl(_DSL)
    widget = EventFlow(flow, source=_DSL)
    assert widget.render_text().plain == render_flow(flow).plain
