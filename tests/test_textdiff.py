from __future__ import annotations

from mdview.diff import parse_diff
from mdview.textdiff import build_unified_diff


def test_identical_strings_yield_empty_diff() -> None:
    assert build_unified_diff("", "") == ""
    assert build_unified_diff("# Title\n\nbody\n", "# Title\n\nbody\n") == ""


def test_change_is_parseable_by_parse_diff() -> None:
    # The generated diff must round-trip through the existing diff parser so the
    # preview can render it with diffview.render_hunk.
    original = "# Title\n\nold line\n"
    edited = "# Title\n\nnew line\n"
    diff = build_unified_diff(original, edited)
    files = parse_diff(diff)
    assert len(files) == 1
    hunks = files[0].hunks
    assert hunks, "expected at least one hunk"
    texts = [line.text for hunk in hunks for line in hunk.lines]
    assert "old line" in texts
    assert "new line" in texts
    kinds = {line.kind for hunk in hunks for line in hunk.lines}
    assert "del" in kinds and "add" in kinds


def test_trailing_newline_difference_is_a_diff() -> None:
    diff = build_unified_diff("body", "body\n")
    assert diff != ""
    # Still parseable (no crash on the missing trailing newline).
    assert parse_diff(diff)


def test_multiline_replacement() -> None:
    original = "a\nb\nc\n"
    edited = "a\nB2\nB3\nc\n"
    diff = build_unified_diff(original, edited)
    files = parse_diff(diff)
    texts = [line.text for hunk in files[0].hunks for line in hunk.lines]
    assert "B2" in texts and "B3" in texts


def test_label_appears_in_header() -> None:
    diff = build_unified_diff("x\n", "y\n", label="§2 概要")
    assert "§2 概要 (original)" in diff
    assert "§2 概要 (edited)" in diff
