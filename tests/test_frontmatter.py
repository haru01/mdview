from mdview.frontmatter import (
    render_document,
    split_frontmatter,
    strip_frontmatter,
    to_markdown,
)


# --- split_frontmatter -----------------------------------------------------


def test_split_returns_inner_and_body():
    inner, body = split_frontmatter("---\ntitle: A\n---\n# H\n\nbody\n")
    assert inner == "title: A\n"
    assert body == "# H\n\nbody\n"


def test_split_accepts_dot_terminator():
    inner, body = split_frontmatter("---\ntitle: A\n...\nbody\n")
    assert inner == "title: A\n"
    assert body == "body\n"


def test_split_none_without_frontmatter():
    assert split_frontmatter("# H\n\nbody\n") == (None, "# H\n\nbody\n")


def test_split_none_when_unterminated():
    text = "---\ntitle: A\nno close\n"
    assert split_frontmatter(text) == (None, text)


def test_split_ignores_hr_not_at_start():
    text = "intro\n\n---\n\nmore\n"
    assert split_frontmatter(text) == (None, text)


# --- strip_frontmatter -----------------------------------------------------


def test_strip_removes_leading_block():
    assert strip_frontmatter("---\ntitle: A\n---\n# H\n") == "# H\n"


def test_strip_leaves_text_without_frontmatter():
    assert strip_frontmatter("# H\nbody\n") == "# H\nbody\n"


# --- to_markdown -----------------------------------------------------------


def test_to_markdown_one_item_per_key():
    out = to_markdown("title: Meta Note\nid: SELF-H-001\n")
    assert out == "> - **title**: Meta Note\n> - **id**: SELF-H-001\n"


def test_to_markdown_empty_value_keeps_colon():
    assert to_markdown("draft:\n") == "> - **draft**:\n"


def test_to_markdown_value_with_colon_splits_once():
    assert to_markdown("time: 10:30\n") == "> - **time**: 10:30\n"


def test_to_markdown_nested_list_items_indent_and_keep_dash():
    out = to_markdown("tags:\n  - spec\n  - draft\n")
    assert out == "> - **tags**:\n>   - spec\n>   - draft\n"


def test_to_markdown_preserves_wikilink_in_value():
    # left intact so the later wikilink rewrite turns it into a clickable link
    assert to_markdown("related: [[wiki_b]]\n") == "> - **related**: [[wiki_b]]\n"


def test_to_markdown_empty_block():
    assert to_markdown("\n  \n") == ""


# --- render_document -------------------------------------------------------


def test_render_document_replaces_block_and_keeps_body():
    out = render_document("---\ntitle: A\n---\n# H\n\nbody\n")
    assert out == "> - **title**: A\n\n# H\n\nbody\n"


def test_render_document_passthrough_without_frontmatter():
    assert render_document("# H\nbody\n") == "# H\nbody\n"
