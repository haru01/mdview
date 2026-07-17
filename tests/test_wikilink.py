from pathlib import Path

from mdview.wikilink import (
    WIKILINK_SCHEME,
    link_href_from_meta,
    parse_wikilink_href,
    resolve_target,
    rewrite_wikilinks,
    wikilinks_from_source,
)


# --- rewrite_wikilinks -----------------------------------------------------


def test_rewrite_basic_wikilink():
    out = rewrite_wikilinks("see [[SELF-H-001]] now")
    assert out == f"see [SELF-H-001]({WIKILINK_SCHEME}SELF-H-001) now"


def test_rewrite_alias_uses_display_text_and_target_href():
    out = rewrite_wikilinks("see [[SELF-H-001|要件H-001]] now")
    assert out == f"see [要件H-001]({WIKILINK_SCHEME}SELF-H-001) now"


def test_rewrite_encodes_spaces_in_target():
    out = rewrite_wikilinks("[[My Note]]")
    assert out == f"[My Note]({WIKILINK_SCHEME}My%20Note)"


def test_rewrite_strips_surrounding_whitespace_in_target_and_display():
    out = rewrite_wikilinks("[[  A  |  B  ]]")
    assert out == f"[B]({WIKILINK_SCHEME}A)"


def test_rewrite_multiple_on_one_line():
    out = rewrite_wikilinks("[[A]] and [[B]]")
    assert out == f"[A]({WIKILINK_SCHEME}A) and [B]({WIKILINK_SCHEME}B)"


def test_rewrite_skips_fenced_code_block():
    text = "before\n```\n[[NotALink]]\n```\nafter [[Real]]"
    out = rewrite_wikilinks(text)
    assert "[[NotALink]]" in out  # untouched inside the fence
    assert f"[Real]({WIKILINK_SCHEME}Real)" in out


def test_rewrite_skips_tilde_fence():
    text = "~~~\n[[NotALink]]\n~~~"
    assert rewrite_wikilinks(text) == text


def test_rewrite_skips_inline_code():
    out = rewrite_wikilinks("code `[[Literal]]` and [[Real]]")
    assert "`[[Literal]]`" in out
    assert f"[Real]({WIKILINK_SCHEME}Real)" in out


def test_rewrite_leaves_plain_text_untouched():
    assert rewrite_wikilinks("no links here") == "no links here"


def test_rewrite_ignores_empty_target():
    assert rewrite_wikilinks("[[]]") == "[[]]"


# --- wikilinks_from_source (reads the rewritten/rendered source) ------------


def test_from_source_returns_target_and_display_pairs():
    rendered = rewrite_wikilinks("[[A]] and [[B|Bee]]")
    assert wikilinks_from_source(rendered) == [("A", "A"), ("B", "Bee")]


def test_from_source_dedupes_by_target_keeping_first_display():
    rendered = rewrite_wikilinks("[[A|first]] then [[A|second]]")
    assert wikilinks_from_source(rendered) == [("A", "first")]


def test_from_source_decodes_encoded_target():
    rendered = rewrite_wikilinks("[[My Note]]")
    assert wikilinks_from_source(rendered) == [("My Note", "My Note")]


def test_from_source_skips_code():
    # code/inline stay literal after rewrite, so no wikilink: link is present
    rendered = rewrite_wikilinks("```\n[[Buried]]\n```\n`[[Inline]]` [[Real]]")
    assert wikilinks_from_source(rendered) == [("Real", "Real")]


# --- parse_wikilink_href ---------------------------------------------------


def test_parse_href_returns_target():
    assert parse_wikilink_href(f"{WIKILINK_SCHEME}SELF-H-001") == "SELF-H-001"


def test_parse_href_returns_none_for_non_wikilink():
    assert parse_wikilink_href("other.md") is None
    assert parse_wikilink_href("https://example.com") is None


def test_parse_href_handles_already_decoded_space():
    # LinkClicked unquotes the href before our handler sees it.
    assert parse_wikilink_href(f"{WIKILINK_SCHEME}My Note") == "My Note"


# --- link_href_from_meta (hover) -------------------------------------------


def test_link_href_from_meta_single_quoted():
    assert link_href_from_meta({"@click": "link('wikilink:wiki_b')"}) == "wikilink:wiki_b"


def test_link_href_from_meta_encoded_target():
    got = link_href_from_meta({"@click": "link('wikilink:My%20Note')"})
    assert got == "wikilink:My%20Note"


def test_link_href_from_meta_none_without_click():
    assert link_href_from_meta({}) is None
    assert link_href_from_meta({"foo": "bar"}) is None
    assert link_href_from_meta("not a dict") is None


# --- resolve_target --------------------------------------------------------


def test_resolve_by_basename_without_extension(tmp_path):
    files = [Path("docs/SELF-H-001.md")]
    got = resolve_target("SELF-H-001", tmp_path, files)
    assert got == tmp_path / "docs/SELF-H-001.md"


def test_resolve_with_explicit_md_extension(tmp_path):
    files = [Path("SELF-H-001.md")]
    assert resolve_target("SELF-H-001.md", tmp_path, files) == tmp_path / "SELF-H-001.md"


def test_resolve_missing_returns_none(tmp_path):
    files = [Path("other.md")]
    assert resolve_target("SELF-H-001", tmp_path, files) is None


def test_resolve_is_case_insensitive(tmp_path):
    files = [Path("Readme.md")]
    assert resolve_target("readme", tmp_path, files) == tmp_path / "Readme.md"


def test_resolve_path_like_target_matches_relative_path(tmp_path):
    files = [Path("docs/guide.md"), Path("guide.md")]
    assert resolve_target("docs/guide", tmp_path, files) == tmp_path / "docs/guide.md"


def test_resolve_tie_break_prefers_shortest_then_lexicographic(tmp_path):
    files = [Path("z/note.md"), Path("a/b/note.md"), Path("m/note.md")]
    # all share basename `note`; shallowest depth wins, ties broken lexicographically
    assert resolve_target("note", tmp_path, files) == tmp_path / "m/note.md"


def test_resolve_empty_target_returns_none(tmp_path):
    assert resolve_target("   ", tmp_path, [Path("a.md")]) is None
