from __future__ import annotations

from rich.text import Text

from mdview.eventflow import parse_flow_dsl
from mdview.eventflowview import (
    ASYNC_ARROW,
    FANOUT_BADGE,
    JOIN_MARK,
    render_flow,
)

_FLOW = parse_flow_dsl(
    """\
title: ハッピーパス
flow:
|community|: 主催者が活動を始める
  @主催者 > !コミュニティを作成 > [コミュニティが作成された] >>
|participation|: 自動承認
  $AutoApprove > [承認された]
"""
)

_FANOUT = parse_flow_dsl(
    """\
title: 中止 Saga
flow:
|ticketing|: BULK 並列返金
  $一括返金 *> !返金を実行 > [返金が完了した] &>>
|event-planning|: Join で確定
  $全返金完了 > [中止が確定した]
"""
)


def test_render_returns_text() -> None:
    assert isinstance(render_flow(_FLOW), Text)


def test_render_includes_title() -> None:
    assert "ハッピーパス" in render_flow(_FLOW).plain


def test_render_includes_lane_name_and_description() -> None:
    plain = render_flow(_FLOW).plain
    assert "community" in plain
    assert "主催者が活動を始める" in plain


def test_render_includes_note_labels() -> None:
    plain = render_flow(_FLOW).plain
    for label in ("主催者", "コミュニティを作成", "コミュニティが作成された", "AutoApprove", "承認された"):
        assert label in plain


def test_render_includes_kind_labels() -> None:
    plain = render_flow(_FLOW).plain
    assert "Actor" in plain
    assert "Command" in plain
    assert "Event" in plain
    assert "Policy" in plain


def test_render_marks_async_lane() -> None:
    # The community lane ends with `>>`, so its band carries the async arrow.
    assert ASYNC_ARROW in render_flow(_FLOW).plain


def test_render_marks_fanout_with_badge() -> None:
    assert FANOUT_BADGE in render_flow(_FANOUT).plain


def test_render_marks_join() -> None:
    assert JOIN_MARK in render_flow(_FANOUT).plain


def test_render_is_multiline() -> None:
    # Sticky-note boxes are multi-row, so a flow renders to several lines.
    assert render_flow(_FLOW).plain.count("\n") >= 3
