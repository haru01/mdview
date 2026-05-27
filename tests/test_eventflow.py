from __future__ import annotations

from mdview.eventflow import parse_dsl_item, parse_flow_dsl, parse_flow_line

# A small flow exercising prefixes, sync (`>`), async (`>>`) and multiple lanes.
_BASIC = """\
title: ハッピーパス
flow:
|community|: 主催者が活動を始める
  @主催者 > !コミュニティを作成 > [コミュニティが作成された] >>
|participation|: 自動承認 or 補欠
  $AutoApprove > !承認する > ?残席数 > [承認された]
"""


# --- parse_dsl_item: element prefixes --------------------------------------


def test_item_actor_prefix() -> None:
    note = parse_dsl_item("@主催者")
    assert note is not None
    assert note.kind == "actor"
    assert note.label == "主催者"


def test_item_command_prefix() -> None:
    note = parse_dsl_item("!コミュニティを作成")
    assert note is not None and note.kind == "command" and note.label == "コミュニティを作成"


def test_item_event_brackets() -> None:
    note = parse_dsl_item("[作成された]")
    assert note is not None and note.kind == "event" and note.label == "作成された"


def test_item_policy_prefix() -> None:
    note = parse_dsl_item("$AutoApprove")
    assert note is not None and note.kind == "policy" and note.label == "AutoApprove"


def test_item_readmodel_prefix() -> None:
    note = parse_dsl_item("?残席数")
    assert note is not None and note.kind == "readmodel" and note.label == "残席数"


def test_item_bare_word_is_command() -> None:
    note = parse_dsl_item("PublishEvent")
    assert note is not None and note.kind == "command" and note.label == "PublishEvent"


def test_item_empty_is_none() -> None:
    assert parse_dsl_item("   ") is None


# --- parse_flow_line: operators --------------------------------------------


def test_line_sync_chain() -> None:
    notes, joins = parse_flow_line("@主催者 > !作成 > [作成された]")
    assert [n.kind for n in notes] == ["actor", "command", "event"]
    assert not joins
    assert not any(n.is_async for n in notes)


def test_line_async_marks_last_note() -> None:
    notes, joins = parse_flow_line("!作成 > [作成された] >>")
    assert not joins
    assert notes[-1].is_async is True
    assert notes[0].is_async is False


def test_line_join_sets_joins_into_next() -> None:
    notes, joins = parse_flow_line("$一括返金 *> !返金を実行 > [返金が完了した] &>>")
    assert joins is True
    # &>> also implies the async end on the last note.
    assert notes[-1].is_async is True


def test_line_fanout_marks_post_star_notes() -> None:
    notes, _ = parse_flow_line("$中止時の一括返金 *> !返金を実行 > [返金が完了した]")
    # The policy before `*>` is not fanout; everything after it is.
    assert notes[0].is_fanout is False
    assert all(n.is_fanout for n in notes[1:])


# --- parse_flow_dsl: full document -----------------------------------------


def test_dsl_title_and_lane_count() -> None:
    flow = parse_flow_dsl(_BASIC)
    assert flow is not None
    assert flow.title == "ハッピーパス"
    assert len(flow.lanes) == 2


def test_dsl_lane_header_fields() -> None:
    flow = parse_flow_dsl(_BASIC)
    assert flow is not None
    lane = flow.lanes[0]
    assert lane.bc_name == "community"
    assert lane.description == "主催者が活動を始める"


def test_dsl_lane_notes_flatten_multiline() -> None:
    flow = parse_flow_dsl(_BASIC)
    assert flow is not None
    labels = [n.label for n in flow.lanes[0].notes]
    assert labels == ["主催者", "コミュニティを作成", "コミュニティが作成された"]
    assert flow.lanes[0].notes[-1].is_async is True


def test_dsl_comment_lines_ignored() -> None:
    flow = parse_flow_dsl("# a comment\ntitle: T\nflow:\n|bc|: d\n  @x > [y]\n")
    assert flow is not None and flow.title == "T" and len(flow.lanes) == 1


def test_dsl_empty_returns_none() -> None:
    assert parse_flow_dsl("title: T\nflow:\n") is None
    assert parse_flow_dsl("") is None
