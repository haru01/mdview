from __future__ import annotations

from pathlib import Path

from mdview.wiki import (
    WikiIndex,
    WikiLink,
    frontmatter_display,
    parse_wikilinks,
    split_frontmatter,
)


# --- split_frontmatter -----------------------------------------------------


_DOC = """\
---
title: LLM Wiki Pattern
type: concept
tags: [learning, research, automation]
confidence: high
---

# LLM Wiki Pattern

Body text.
"""


def test_split_frontmatter_separates_prefix_meta_and_body():
    split = split_frontmatter(_DOC)

    assert split.meta["title"] == "LLM Wiki Pattern"
    assert split.meta["type"] == "concept"
    assert split.meta["tags"] == ["learning", "research", "automation"]
    assert split.meta["confidence"] == "high"
    assert split.body.startswith("\n# LLM Wiki Pattern")


def test_split_frontmatter_round_trips():
    split = split_frontmatter(_DOC)

    assert split.raw_prefix is not None
    assert split.raw_prefix + split.body == _DOC


def test_split_frontmatter_no_frontmatter_is_identity():
    text = "# Just a heading\n\nNo frontmatter here.\n"

    split = split_frontmatter(text)

    assert split.raw_prefix is None
    assert split.meta == {}
    assert split.body == text


def test_split_frontmatter_missing_closing_delimiter_is_identity():
    text = "---\ntitle: broken\n\n# Heading\n"

    split = split_frontmatter(text)

    assert split.raw_prefix is None
    assert split.body == text


def test_split_frontmatter_empty_block():
    text = "---\n---\n# Heading\n"

    split = split_frontmatter(text)

    assert split.meta == {}
    assert split.raw_prefix is not None
    assert split.raw_prefix + split.body == text


# --- parse_wikilinks -------------------------------------------------------


def test_parse_wikilinks_plain():
    links = parse_wikilinks("see [[claude-code]] for more")

    assert links == [WikiLink(start=4, end=19, target="claude-code", anchor="", alias="claude-code")]


def test_parse_wikilinks_alias():
    (link,) = parse_wikilinks("[[claude-code|Claude Code]]")

    assert link.target == "claude-code"
    assert link.alias == "Claude Code"
    assert link.anchor == ""


def test_parse_wikilinks_anchor():
    (link,) = parse_wikilinks("[[claude-code#usage]]")

    assert link.target == "claude-code"
    assert link.anchor == "usage"
    assert link.alias == "claude-code"


def test_parse_wikilinks_anchor_and_alias():
    (link,) = parse_wikilinks("[[claude-code#usage|How to use]]")

    assert link.target == "claude-code"
    assert link.anchor == "usage"
    assert link.alias == "How to use"


def test_parse_wikilinks_multiple_with_spans():
    text = "[[a]] and [[b]]"

    links = parse_wikilinks(text)

    assert [l.target for l in links] == ["a", "b"]
    assert text[links[0].start : links[0].end] == "[[a]]"
    assert text[links[1].start : links[1].end] == "[[b]]"


def test_parse_wikilinks_none():
    assert parse_wikilinks("no links here [x](y)") == []


# --- frontmatter_display ---------------------------------------------------


def test_frontmatter_display_extracts_title_tags_sources():
    meta = {
        "title": "LLM Wiki Pattern",
        "type": "concept",
        "tags": ["learning", "research"],
        "sources": ["raw/articles/zenn-iepyon-llm-wiki.md"],
        "confidence": "high",
    }

    d = frontmatter_display(meta)

    assert d.title == "LLM Wiki Pattern"
    assert d.tags == ["learning", "research"]
    assert d.sources == ["zenn-iepyon-llm-wiki"]  # stem of the source path


def test_frontmatter_display_meta_line_keeps_scalar_order_without_special_keys():
    meta = {
        "title": "X",
        "type": "concept",
        "tags": ["a"],
        "created": "2026-06-06",
        "updated": "2026-06-07",
        "confidence": "high",
    }

    d = frontmatter_display(meta)

    # title/tags/sources are rendered separately, not in the scalar meta line;
    # the rest keep frontmatter order.
    assert d.meta_line == "type: concept · created: 2026-06-06 · updated: 2026-06-07 · confidence: high"


def test_frontmatter_display_handles_scalar_tags_and_sources():
    d = frontmatter_display({"tags": "solo", "sources": "notes/x.md"})

    assert d.tags == ["solo"]
    assert d.sources == ["x"]


def test_frontmatter_display_empty_meta():
    d = frontmatter_display({})

    assert d.title is None
    assert d.tags == []
    assert d.sources == []
    assert d.meta_line == ""


# --- WikiIndex -------------------------------------------------------------


def _write(path: Path, tags: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if tags is not None:
        path.write_text(
            f"---\ntitle: {path.stem}\ntags: [{', '.join(tags)}]\n---\n\n# {path.stem}\n"
        )
    else:
        path.write_text(f"# {path.stem}\n")


def test_wiki_index_resolves_by_stem(tmp_path):
    _write(tmp_path / "wiki" / "concepts" / "claude-code.md")
    _write(tmp_path / "wiki" / "index.md")

    index = WikiIndex.build(tmp_path)

    assert index.resolve("claude-code") == [
        tmp_path / "wiki" / "concepts" / "claude-code.md"
    ]


def test_wiki_index_resolve_ambiguous_returns_all(tmp_path):
    _write(tmp_path / "a" / "dup.md")
    _write(tmp_path / "b" / "dup.md")

    index = WikiIndex.build(tmp_path)

    assert set(index.resolve("dup")) == {
        tmp_path / "a" / "dup.md",
        tmp_path / "b" / "dup.md",
    }


def test_wiki_index_resolve_missing_returns_empty(tmp_path):
    _write(tmp_path / "x.md")

    index = WikiIndex.build(tmp_path)

    assert index.resolve("nope") == []


def test_wiki_index_files_with_tag(tmp_path):
    _write(tmp_path / "a.md", tags=["learning", "research"])
    _write(tmp_path / "b.md", tags=["research"])
    _write(tmp_path / "c.md", tags=["other"])

    index = WikiIndex.build(tmp_path)

    assert index.files_with_tag("research") == [tmp_path / "a.md", tmp_path / "b.md"]
    assert index.files_with_tag("learning") == [tmp_path / "a.md"]
    assert index.files_with_tag("missing") == []
