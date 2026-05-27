from __future__ import annotations

from mdview.search import compile_query


def test_empty_query_is_none() -> None:
    assert compile_query("") is None


def test_query_is_case_insensitive() -> None:
    pattern = compile_query("Hello")
    assert pattern is not None
    assert pattern.search("say hello world")


def test_invalid_regex_falls_back_to_literal() -> None:
    # An unbalanced paren is not a valid regex; it must match literally instead
    # of raising, so a half-typed pattern still searches for the characters.
    pattern = compile_query("a(")
    assert pattern is not None
    assert pattern.search("formula a( b")
    assert not pattern.search("plain text")


def test_at_space_matches_both_file_and_hunk() -> None:
    # `@\s` (unanchored) hits the file heading's `@ ` and the second `@` of a
    # `@@ ` hunk header — the documented "both" behaviour.
    pattern = compile_query(r"@\s")
    assert pattern is not None
    assert pattern.search("@ src/app.py")
    assert pattern.search("@@ -1,4 +1,4 @@ def main():")


def test_double_at_matches_only_hunk() -> None:
    pattern = compile_query("@@")
    assert pattern is not None
    assert pattern.search("@@ -1,4 +1,4 @@")
    assert not pattern.search("@ src/app.py")


def test_anchored_at_matches_only_file_heading() -> None:
    # `^@ ` anchors at the start of the block text: the file heading starts with
    # `@ `, the hunk header starts with `@@`, so only the file heading matches.
    pattern = compile_query("^@ ")
    assert pattern is not None
    assert pattern.search("@ src/app.py")
    assert not pattern.search("@@ -1,4 +1,4 @@")
