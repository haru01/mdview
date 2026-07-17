"""Pure helpers for Obsidian-style ``[[wikilink]]`` support.

Framework-free so it can be unit-tested without a TUI (the Textual wiring —
click routing and the peek modal — lives in ``app.py``). Three concerns:

- **rewrite** ``[[Target]]`` / ``[[Target|Display]]`` in raw Markdown to a
  standard link ``[Display](wikilink:Target)`` *before* the document is parsed,
  reusing the existing link-click machinery. The ``wikilink:`` sentinel scheme
  tells the click handler to resolve by note *name* (Obsidian-style) rather than
  directory-relative like a normal ``[..](x.md)`` link. The rewrite deliberately
  skips fenced code blocks and inline code spans so a literal ``[[x]]`` shown in
  a code sample survives verbatim.
- **extract** the ``(target, display)`` pairs from a document (for the ``p``
  peek picker), with the same code-skipping.
- **resolve** a bare note name to a file the way Obsidian resolves a vault link:
  by basename anywhere under the root (or by relative path for a ``dir/note``
  target), case-insensitively, with a deterministic tie-break.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote, unquote

# Sentinel URL scheme for a rewritten wikilink. Chosen so it never collides with
# a real relative link (which keeps its ``.md`` suffix and resolves against the
# viewed document's directory) — the click handler branches on this prefix.
WIKILINK_SCHEME = "wikilink:"

# `[[target]]` or `[[target|display]]`. Target/display can't contain the wiki
# brackets themselves; the first `|` splits target from display (a later `|` is
# part of the display text, matching Obsidian).
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|]+?)(?:\|([^\[\]]*))?\]\]")

# A run of >=3 backticks or tildes at the start of a line opens/closes a fenced
# code block. We only compare the fence character, not the exact length — good
# enough for the viewer's inputs (authored Markdown, not adversarial fences).
_FENCE_RE = re.compile(r"[ \t]*(`{3,}|~{3,})")

# Markdown extensions a wikilink target may resolve to.
_MD_SUFFIXES = frozenset({".md", ".markdown", ".mdown", ".mkd"})


def _has_md_suffix(name: str) -> bool:
    return Path(name).suffix.lower() in _MD_SUFFIXES


def _replace_in_segment(segment: str) -> str:
    """Rewrite every wikilink in a code-free text *segment*."""

    def repl(m: re.Match[str]) -> str:
        target = m.group(1).strip()
        if not target:
            return m.group(0)  # `[[]]` — not a link
        display = (m.group(2) or "").strip() or target
        # Encode the target so a space/special char in the href survives
        # markdown-it parsing; `LinkClicked` unquotes it back before our handler.
        return f"[{display}]({WIKILINK_SCHEME}{quote(target)})"

    return _WIKILINK_RE.sub(repl, segment)


def _process_line(line: str) -> str:
    """Rewrite wikilinks in *line*, skipping inline code spans.

    An inline code span is a run of N backticks closed by the next run of the
    same length; its contents (including any ``[[x]]``) are copied verbatim.
    """
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            run = "`" * (j - i)
            close = line.find(run, j)
            if close != -1:
                out.append(line[i : close + len(run)])  # code span, verbatim
                i = close + len(run)
            else:
                out.append(line[i:j])  # unterminated backtick run
                i = j
        else:
            k = line.find("`", i)
            if k == -1:
                k = n
            out.append(_replace_in_segment(line[i:k]))
            i = k
    return "".join(out)


def _iter_non_code_lines(text: str):
    """Yield ``(line, in_fence)`` for each line, tracking fenced code blocks."""
    fence: str | None = None
    for line in text.splitlines(keepends=True):
        m = _FENCE_RE.match(line)
        marker = m.group(1)[0] if m else None
        if fence is None:
            if marker is not None:
                fence = marker
                yield line, True
            else:
                yield line, False
        else:
            if marker == fence:
                fence = None
            yield line, True


def rewrite_wikilinks(text: str) -> str:
    """Rewrite ``[[target]]`` / ``[[target|display]]`` to standard Markdown links.

    Fenced code blocks and inline code spans are left untouched so a literal
    wikilink in a code sample renders as written.
    """
    if "[[" not in text:
        return text
    out: list[str] = []
    for line, in_fence in _iter_non_code_lines(text):
        out.append(line if in_fence else _process_line(line))
    return "".join(out)


# A wikilink after rewriting: `[display](wikilink:encoded-target)`. Used to
# recover the links from the already-rendered document source for the peek picker
# (the raw `[[..]]` form is gone by then). Display can't contain brackets.
_RENDERED_WIKILINK_RE = re.compile(
    r"\[([^\[\]]*)\]\(" + re.escape(WIKILINK_SCHEME) + r"([^)]*)\)"
)


def wikilinks_from_source(rendered: str) -> list[tuple[str, str]]:
    """Return ``(target, display)`` for each wikilink in *rendered* source.

    Operates on the post-rewrite document source (what's actually rendered and
    clickable), so it always matches the live links regardless of how the source
    got there. Deduped by target, in first-appearance order.
    """
    seen: dict[str, str] = {}
    for m in _RENDERED_WIKILINK_RE.finditer(rendered):
        target = unquote(m.group(2))
        if not target:
            continue
        seen.setdefault(target, m.group(1))
    return list(seen.items())


# A rendered link's click action, as Textual stores it in a style's meta:
# `link('the-href')` (see textual's _markdown.py `action = f"link({href!r})"`).
_LINK_ACTION_RE = re.compile(r"""^link\((['"])(?P<href>.*)\1\)$""")


def link_href_from_meta(meta: dict) -> str | None:
    """Extract a link's href from a Textual style ``meta`` dict, else ``None``.

    Used by the hover handler: a ``MouseMove`` event carries the style under the
    cursor, whose ``@click`` entry is the clickable link's action. The href here
    is still URL-encoded (unlike ``LinkClicked``, which unquotes) — the caller
    unquotes before :func:`parse_wikilink_href`.
    """
    if not isinstance(meta, dict):
        return None
    action = meta.get("@click")
    if not isinstance(action, str):
        return None
    m = _LINK_ACTION_RE.match(action)
    return m.group("href") if m else None


def parse_wikilink_href(href: str) -> str | None:
    """Return the note-name target of a ``wikilink:`` href, else ``None``.

    The href reaching the click handler is already URL-decoded (Textual's
    ``LinkClicked`` unquotes it), so this just strips the scheme.
    """
    if not href.startswith(WIKILINK_SCHEME):
        return None
    return href[len(WIKILINK_SCHEME) :]


def resolve_target(target: str, root: Path, files: list[Path]) -> Path | None:
    """Resolve a wikilink *target* to an absolute file under *root*.

    *files* are root-relative paths (as from ``quickopen.list_viewable_files``).
    A ``dir/note`` target matches by relative path; a bare ``note`` matches by
    basename anywhere in the vault. Matching is case-insensitive and the ``.md``
    extension is optional. On multiple matches the shallowest path wins, ties
    broken lexicographically, so resolution is deterministic.
    """
    target = target.strip()
    if not target:
        return None

    wanted = {target.lower()}
    if not _has_md_suffix(target):
        wanted |= {(target + suffix).lower() for suffix in _MD_SUFFIXES}

    path_like = "/" in target
    matches: list[Path] = []
    for rel in files:
        key = rel.as_posix().lower() if path_like else rel.name.lower()
        if key in wanted:
            matches.append(rel)
    if not matches:
        return None
    matches.sort(key=lambda p: (len(p.parts), p.as_posix()))
    return root / matches[0]
