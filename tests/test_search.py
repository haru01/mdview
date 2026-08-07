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


def test_character_class_is_honoured() -> None:
    # A valid regex is compiled as one, so `\s` and friends work as typed.
    pattern = compile_query(r"TODO:\s")
    assert pattern is not None
    assert pattern.search("TODO: write the docs")
    assert not pattern.search("TODO:write the docs")


def test_anchor_matches_only_at_block_start() -> None:
    # `^` anchors at the start of the block text a search runs against.
    pattern = compile_query("^Note")
    assert pattern is not None
    assert pattern.search("Note: read this first")
    assert not pattern.search("See the Note above")
