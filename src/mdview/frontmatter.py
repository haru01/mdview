"""Readable rendering of a Markdown file's leading YAML frontmatter.

Textual's Markdown parser has no frontmatter plugin, so a leading ``---`` … ``---``
block renders as a mangled setext heading — every key collapsed onto one line.
This module splits that block off and re-emits it as a readable **blockquote
list** (one ``key: value`` per line) that flows through the normal Markdown
pipeline, so any ``[[wikilink]]`` or URL in a value stays clickable.

Pure/framework-free (the app calls it from ``_source_for``). Line-based, not a
real YAML parser: it renders the block readably without interpreting types, which
is all the viewer needs.
"""

from __future__ import annotations

import re

# `key: value` on a frontmatter line (value may be empty). Non-greedy key so a
# value containing `:` (e.g. `time: 10:30`) splits on the first colon only.
_KEY_VALUE = re.compile(r"^\s*([^:]+?):\s*(.*)$")


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Split *text* into ``(frontmatter_inner, body)``.

    Returns ``(None, text)`` when there's no frontmatter — i.e. the first line
    isn't ``---``, or the block is never closed (so we don't swallow a whole
    document that merely starts with a horizontal rule).
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            inner = "".join(lines[1:i])
            body = "".join(lines[i + 1 :]).lstrip("\n")
            return inner, body
    return None, text  # unterminated: not frontmatter


def strip_frontmatter(text: str) -> str:
    """The document body with any leading YAML frontmatter removed."""
    return split_frontmatter(text)[1]


def to_markdown(inner: str) -> str:
    """Render a frontmatter block *inner* as a readable blockquote list.

    Each ``key: value`` becomes a bold-keyed list item; nested/list lines keep
    their own dash and indentation (2 spaces = one level). Returns ``""`` for an
    empty block.
    """
    items: list[str] = []
    for raw in inner.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        depth = (len(line) - len(stripped)) // 2
        indent = "  " * depth
        if stripped == "-" or stripped.startswith("- "):
            items.append(f"> {indent}{stripped}")  # keep the YAML list dash
            continue
        m = _KEY_VALUE.match(line)
        if m:
            key = m.group(1).strip()
            value = m.group(2).strip()
            body = f"**{key}**:" + (f" {value}" if value else "")
            items.append(f"> {indent}- {body}")
        else:
            items.append(f"> {indent}- {stripped}")
    if not items:
        return ""
    return "\n".join(items) + "\n"


def render_document(text: str) -> str:
    """Return *text* with any leading frontmatter re-rendered readably.

    No frontmatter → *text* unchanged. Otherwise the readable blockquote list
    replaces the raw ``---`` block, followed by a blank line and the body.
    """
    inner, body = split_frontmatter(text)
    if inner is None:
        return text
    rendered = to_markdown(inner)
    return f"{rendered}\n{body}" if rendered else body
