from __future__ import annotations

from textual.selection import SELECT_ALL

from mdview.diff import parse_diff, parse_hunk_lines
from mdview.diff_widget import DiffHunk

_BASIC = (
    "diff --git a/src/app.py b/src/app.py\n"
    "--- a/src/app.py\n+++ b/src/app.py\n"
    "@@ -1,4 +1,4 @@ def main():\n"
    "   import os\n"
    '-  print("old")\n'
    '+  print("new")\n'
    "   return 0\n"
)


def test_get_selection_returns_clean_unified_diff() -> None:
    # The display has a line-number gutter, but selecting the hunk must yield a
    # valid unified diff (markers kept, no gutter) so Ask AI / copy stay useful.
    h = parse_diff(_BASIC)[0].hunks[0]
    widget = DiffHunk(h, file_path="src/app.py")
    text, ending = widget.get_selection(SELECT_ALL)
    assert text == h.raw
    assert "  1" not in text  # no gutter line numbers leaked into the selection
    assert ending == "\n"


def test_get_selection_works_without_file_path() -> None:
    h = parse_hunk_lines("-old\n+new\n")
    widget = DiffHunk(h, file_path=None)
    text, _ = widget.get_selection(SELECT_ALL)
    assert text == "-old\n+new"
