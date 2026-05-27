from __future__ import annotations

from mdview.edit_apply import replace_line_range, selection_block_range


def test_replace_middle_section_preserves_blank_separator() -> None:
    doc = "# Title\n\n## A\nold body\n\n## B\ntail\n"
    lines = doc.splitlines(keepends=True)
    # Section A is lines [2, 5): "## A\n", "old body\n", "\n".
    assert lines[2:5] == ["## A\n", "old body\n", "\n"]
    out = replace_line_range(doc, 2, 5, "## A\nnew body")
    assert out == "# Title\n\n## A\nnew body\n\n## B\ntail\n"


def test_replace_at_eof_without_trailing_newline() -> None:
    doc = "# Title\n\n## A\nbody"  # no final newline
    out = replace_line_range(doc, 2, 4, "## A\nnew body")
    assert out == "# Title\n\n## A\nnew body"


def test_replace_whole_document_preserves_final_newline() -> None:
    doc = "old\n"
    out = replace_line_range(doc, 0, 1, "new")
    assert out == "new\n"  # the document's trailing newline run is preserved


def test_replace_keeps_following_block_on_its_own_line() -> None:
    # Removed span has no trailing blank line, but content follows → a newline is
    # inserted so the next block doesn't merge onto the edited line.
    doc = "## A\nbody\n## B\n"
    out = replace_line_range(doc, 0, 2, "## A\nedited")
    assert out == "## A\nedited\n## B\n"


def test_selection_block_range_single_block() -> None:
    assert selection_block_range([(3, 5)], "a\nb\nc\nd\ne\nf\n") == (3, 5)


def test_selection_block_range_blank_gap_is_contiguous() -> None:
    # Two paragraphs separated by a blank line (line 1) → one slice [0, 3).
    doc = "para1\n\npara2\n"
    assert selection_block_range([(0, 1), (2, 3)], doc) == (0, 3)


def test_selection_block_range_real_content_gap_is_none() -> None:
    # Lines 1-2 between the two selected blocks hold real content that is NOT
    # selected → not a single replaceable slice.
    doc = "a\nMIDDLE\nb\nc\n"
    assert selection_block_range([(0, 1), (2, 3)], doc) is None


def test_selection_block_range_empty_is_none() -> None:
    assert selection_block_range([], "a\nb\n") is None
