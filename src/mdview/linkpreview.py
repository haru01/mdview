"""Pure helpers for the hover preview of *ordinary* Markdown links.

The `[[wikilink]]` hover preview (``wiki.wikilink_action_target`` + the popup in
``app.py``) only knows about wiki spans. Textual renders a plain
``[text](target)`` link as a span carrying ``@click=link('target')`` instead, so
recovering *that* href is the entry point for previewing normal links too.

Three concerns, all framework-free so they can be unit-tested without a TUI (the
Textual wiring — reading the file, rendering and positioning the popup — stays in
``app.py``):

- ``markdown_link_href`` — recover the href from Textual's ``link('href')``
  action string (the inverse of what ``Markdown`` puts in the style meta).
- ``is_external_href`` — tell a URL (``https:``/``mailto:``…) from a document
  path, so an external link previews as "where it goes" rather than a file read.
- ``section_preview`` — slice the section a ``#anchor`` points at out of a
  document body, so ``[x](notes.md#section)`` peeks at that section rather than
  the top of the file.
"""

from __future__ import annotations

import ast
import re
from string import punctuation

# Textual builds a link span's action as `f"link({href!r})"` — a Python string
# literal, so the quoting depends on the href. Anchored at both ends so a
# wikilink's `app.wikilink('name','')` (which *contains* `link(`) can't match.
_LINK_ACTION_RE = re.compile(r"\Alink\((.*)\)\Z", re.DOTALL)

# A URI scheme prefix (`https:`, `mailto:`, `data:`…). A bare Windows-style
# `C:\...` isn't a concern here: single-letter schemes are excluded by requiring
# at least two characters.
_SCHEME_RE = re.compile(r"\A[A-Za-z][A-Za-z0-9+.\-]+:")

# An ATX heading line, with any closing `#`s stripped off the title.
_HEADING_RE = re.compile(r"\A(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*\Z")
_FENCE_RE = re.compile(r"\A[ \t]*(```|~~~)")

# Slug rules mirroring Textual's `_slug.slug` (GitHub-flavoured): drop
# punctuation except `-`/`_`, then whitespace becomes `-`. Kept local rather than
# imported so this module stays framework-free (and off Textual's private API);
# the percent-encoding Textual adds is skipped, since we compare slug-to-slug —
# which also lets a non-ASCII anchor (`#見出し`) match its heading.
_SLUG_REMOVABLE = punctuation.replace("-", "").replace("_", "")
_SLUG_STRIP_RE = re.compile(f"[{re.escape(_SLUG_REMOVABLE)}]+")
_SLUG_SPACE_RE = re.compile(r"\s+")


def markdown_link_href(action: str | None) -> str | None:
    """Recover the href from a Markdown link's ``link('href')`` action, else ``None``.

    Textual's `Markdown` stylizes every ``[text](href)`` (and image) with
    ``@click=link({href!r})``; this is the inverse, used by the hover handler to
    identify the link under the cursor. Any other action (a wikilink, a tag chip,
    a section-insight marker) returns ``None``.
    """
    if not action:
        return None
    match = _LINK_ACTION_RE.match(action.strip())
    if match is None:
        return None
    try:
        href = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return None
    return href if isinstance(href, str) else None


def is_external_href(href: str) -> bool:
    """True for an href the viewer can't read off disk (``https:``, ``mailto:``…)."""
    return bool(_SCHEME_RE.match(href))


def slugify(text: str) -> str:
    """A heading anchor slug (see ``_SLUG_STRIP_RE``); applied to both sides of a
    comparison so ``#My Heading``, ``#my-heading`` and the heading itself agree."""
    result = _SLUG_STRIP_RE.sub("", text.strip().lower())
    return _SLUG_SPACE_RE.sub("-", result).strip("-")


def section_preview(body: str, anchor: str) -> str | None:
    """The Markdown of *body*'s section whose heading matches *anchor*.

    The section runs from its heading down to the next heading of equal or higher
    level (the same span the viewer treats as a section elsewhere). Headings
    inside fenced code blocks are ignored. Repeated headings get Textual's
    ``-1``/``-2`` suffix disambiguation, so ``#notes-1`` is the *second* "Notes".
    Returns ``None`` when nothing matches (the caller falls back to the body).
    """
    wanted = slugify(anchor)
    if not wanted:
        return None
    lines = body.splitlines()
    headings: list[tuple[int, int, str]] = []  # (line index, level, slug)
    used: dict[str, int] = {}
    fence: str | None = None
    for i, line in enumerate(lines):
        fence_match = _FENCE_RE.match(line)
        if fence_match is not None:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        heading = _HEADING_RE.match(line)
        if heading is None:
            continue
        base = slugify(heading.group(2))
        seen = used.get(base, 0)
        used[base] = seen + 1
        headings.append((i, len(heading.group(1)), f"{base}-{seen}" if seen else base))

    for pos, (start, level, slug) in enumerate(headings):
        if slug != wanted:
            continue
        end = len(lines)
        for next_start, next_level, _ in headings[pos + 1 :]:
            if next_level <= level:
                end = next_start
                break
        return "\n".join(lines[start:end]).strip("\n")
    return None
