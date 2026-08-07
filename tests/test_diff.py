from __future__ import annotations

from mdview.diff import parse_hunks
from mdview.textdiff import build_unified_diff

# The only shape `parse_hunks` ever sees in production: difflib's plain unified
# diff, two headers then one or more `@@` blocks.
_BASIC = build_unified_diff(
    "import os\nprint(\"old\")\nreturn 0\n",
    "import os\nprint(\"new\")\nreturn 0\n",
    label="src/app.py",
)


def test_parse_hunks_finds_one_hunk_and_keeps_its_header() -> None:
    hunks = parse_hunks(_BASIC)
    assert len(hunks) == 1
    assert hunks[0].header.startswith("@@ -1,3 +1,3 @@")


def test_parse_hunks_classifies_lines_and_numbers() -> None:
    got = [(ln.kind, ln.old_no, ln.new_no, ln.text) for ln in parse_hunks(_BASIC)[0].lines]
    assert got == [
        ("context", 1, 1, "import os"),
        ("del", 2, None, 'print("old")'),
        ("add", None, 2, 'print("new")'),
        ("context", 3, 3, "return 0"),
    ]


def test_parse_hunks_skips_the_file_header_lines() -> None:
    texts = [ln.text for ln in parse_hunks(_BASIC)[0].lines]
    assert not any(t.startswith(("---", "+++")) for t in texts)


def test_parse_hunks_splits_distant_changes_into_separate_hunks() -> None:
    original = "\n".join(str(i) for i in range(40)) + "\n"
    edited = original.replace("0\n", "ZERO\n", 1).replace("39\n", "THIRTYNINE\n")
    hunks = parse_hunks(build_unified_diff(original, edited))
    assert len(hunks) == 2
    # Each hunk is numbered from its own `@@` start, not from the document top.
    assert hunks[1].lines[0].old_no > hunks[0].lines[-1].old_no


def test_parse_hunks_without_a_header_is_empty() -> None:
    assert parse_hunks("just some prose\nwith no @@ block\n") == []


def test_parse_hunks_crlf() -> None:
    diff = "--- a\r\n+++ b\r\n@@ -1 +1 @@\r\n-a\r\n+b\r\n"
    kinds = [ln.kind for ln in parse_hunks(diff)[0].lines]
    assert kinds == ["del", "add"]


def test_parse_hunks_form_feed_in_body_survives() -> None:
    # `str.splitlines()` would break on \x0c and strip the line's +/- marker.
    diff = "--- a\n+++ b\n@@ -1 +1 @@\n+foo\x0cbar\n"
    line = parse_hunks(diff)[0].lines[0]
    assert line.kind == "add"
    assert line.text == "foo\x0cbar"


def test_parse_hunks_blank_context_line_is_context() -> None:
    diff = "--- a\n+++ b\n@@ -1,2 +1,2 @@\n\n-x\n+y\n"
    kinds = [ln.kind for ln in parse_hunks(diff)[0].lines]
    assert kinds == ["context", "del", "add"]
