from __future__ import annotations

from mdview.diff import parse_diff, parse_hunk_lines
from mdview.diffview import ADD_BG, DEL_BG, guess_lexer, hunk_plain_text, render_hunk

_BASIC = (
    "diff --git a/src/app.py b/src/app.py\n"
    "--- a/src/app.py\n+++ b/src/app.py\n"
    "@@ -1,4 +1,4 @@ def main():\n"
    "   import os\n"
    '-  print("old")\n'
    '+  print("new")\n'
    "   return 0\n"
)


def test_hunk_plain_text_is_the_raw_diff() -> None:
    # Selection / Ask AI must receive a valid unified diff (markers kept, no
    # line-number gutter): that is exactly `hunk.raw`.
    h = parse_diff(_BASIC)[0].hunks[0]
    assert hunk_plain_text(h) == h.raw


def test_render_hunk_shows_header_numbers_markers_and_code() -> None:
    h = parse_diff(_BASIC)[0].hunks[0]
    plain = render_hunk(h, file_path="src/app.py").plain
    # the @@ header is shown as a line, not promoted to a markdown heading
    assert "@@ -1,4 +1,4 @@ def main():" in plain
    assert "import os" in plain
    assert 'print("new")' in plain
    # line-number gutter present
    assert "1" in plain and "3" in plain
    # +/- markers shown in the display
    assert "-" in plain and "+" in plain


def test_render_hunk_backgrounds_added_and_removed_lines() -> None:
    h = parse_diff(_BASIC)[0].hunks[0]
    text = render_hunk(h, file_path="src/app.py")
    styles = " ".join(str(span.style) for span in text.spans)
    assert ADD_BG in styles, "added line should carry the add background"
    assert DEL_BG in styles, "removed line should carry the del background"


def test_render_hunk_syntax_highlights_code() -> None:
    h = parse_diff(_BASIC)[0].hunks[0]
    text = render_hunk(h, file_path="src/app.py")
    # python highlighting adds foreground colour spans beyond the bg overlays
    assert len(text.spans) > 2


def test_render_hunk_handles_headerless_fence() -> None:
    h = parse_hunk_lines("-old\n+new\n unchanged\n")
    plain = render_hunk(h, file_path=None).plain
    assert "old" in plain and "new" in plain and "unchanged" in plain


def test_guess_lexer_from_filename() -> None:
    assert guess_lexer("x.py") == "python"


def test_guess_lexer_none_returns_none() -> None:
    assert guess_lexer(None) is None
