from __future__ import annotations

from mdview.diff import parse_hunks
from mdview.diffview import ADD_BG, DEL_BG, guess_lexer, render_hunk
from mdview.textdiff import build_unified_diff

_HUNK = parse_hunks(
    build_unified_diff(
        'import os\nprint("old")\nreturn 0\n',
        'import os\nprint("new")\nreturn 0\n',
        label="src/app.py",
    )
)[0]


def test_render_hunk_shows_header_numbers_markers_and_code() -> None:
    plain = render_hunk(_HUNK, file_path="src/app.py").plain
    # the @@ header is shown as a line, not promoted to a markdown heading
    assert "@@ -1,3 +1,3 @@" in plain
    assert "import os" in plain
    assert 'print("new")' in plain
    # line-number gutter present
    assert "1" in plain and "3" in plain
    # +/- markers shown in the display
    assert "-" in plain and "+" in plain


def test_render_hunk_backgrounds_added_and_removed_lines() -> None:
    text = render_hunk(_HUNK, file_path="src/app.py")
    styles = " ".join(str(span.style) for span in text.spans)
    assert ADD_BG in styles, "added line should carry the add background"
    assert DEL_BG in styles, "removed line should carry the del background"


def test_render_hunk_syntax_highlights_code() -> None:
    text = render_hunk(_HUNK, file_path="src/app.py")
    # python highlighting adds foreground colour spans beyond the bg overlays
    assert len(text.spans) > 2


def test_render_hunk_pads_every_line_to_the_same_width() -> None:
    # The background bars must span the full block, so short lines are padded.
    lines = render_hunk(_HUNK, file_path="src/app.py").plain.split("\n")
    assert len({len(line) for line in lines}) == 1


def test_guess_lexer_from_filename() -> None:
    assert guess_lexer("x.py") == "python"


def test_guess_lexer_none_returns_none() -> None:
    assert guess_lexer(None) is None
