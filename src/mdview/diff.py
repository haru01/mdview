"""Split a unified diff into hunks of classified, line-numbered lines.

Deliberately narrow: the only producer is `textdiff.build_unified_diff`, which
wraps `difflib.unified_diff`, and the only consumer is the AI edit preview
(`diff_preview.DiffPreviewScreen` → `diffview.render_hunk`). difflib emits a
plain two-header diff (`--- …` / `+++ …`) for a single "file" and never the
git-only constructs — `diff --git`, mode/rename lines, `Binary files …`,
`a/`/`b/` path prefixes — so none of that is parsed here. Pure and framework-
free; the parse is deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A hunk header: `@@ -12,3 +12,4 @@ optional context`
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
# Capture the old/new start line numbers from a hunk header.
_HUNK_START_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class DiffLine:
    """One body line of a hunk, classified and line-numbered."""

    kind: str  # "context" | "add" | "del"
    old_no: int | None
    new_no: int | None
    text: str  # the line content with its leading +/-/space marker stripped


@dataclass
class Hunk:
    """A single `@@ … @@` hunk: its header line and classified body lines."""

    header: str  # the full `@@ -.. +.. @@ context` line ("" if unknown)
    lines: list[DiffLine] = field(default_factory=list)


def _lines(text: str) -> list[str]:
    """Split *text* on newlines only.

    `str.splitlines()` also breaks on form-feed (\\x0c), vertical-tab (\\x0b),
    NEL and the Unicode line separators, which would corrupt a diff body line
    that happens to contain those bytes (the fragment would lose its `+`/`-`
    prefix). We split on `\\n` and trim a trailing `\\r` so CRLF still works.
    """
    parts = text.split("\n")
    if parts and parts[-1] == "":  # drop the empty trailing element from a final \n
        parts.pop()
    return [p[:-1] if p.endswith("\r") else p for p in parts]


def _build_hunk(header: str, body: list[str]) -> Hunk:
    """Classify *body* lines against *header*, numbering old/new sides."""
    start = _HUNK_START_RE.match(header)
    old_no, new_no = (int(start.group(1)), int(start.group(2))) if start else (1, 1)
    lines: list[DiffLine] = []
    for line in body:
        marker = line[:1]
        if marker == "+":
            lines.append(DiffLine("add", None, new_no, line[1:]))
            new_no += 1
        elif marker == "-":
            lines.append(DiffLine("del", old_no, None, line[1:]))
            old_no += 1
        else:  # " " context, or a bare blank line
            text = line[1:] if marker == " " else line
            lines.append(DiffLine("context", old_no, new_no, text))
            old_no += 1
            new_no += 1
    return Hunk(header=header, lines=lines)


def parse_hunks(text: str) -> list[Hunk]:
    """Parse every `@@ … @@` hunk in *text*, in order.

    Anything outside a hunk (the `---`/`+++` header pair, or stray lines) is
    skipped, so the caller can hand over a whole diff. A change spanning distant
    line ranges yields one `Hunk` per `@@` block.
    """
    lines = _lines(text)
    n = len(lines)
    hunks: list[Hunk] = []
    i = 0
    while i < n:
        if not _HUNK_RE.match(lines[i]):
            i += 1
            continue
        header = lines[i]
        i += 1
        body: list[str] = []
        while i < n and not _HUNK_RE.match(lines[i]):
            body.append(lines[i])
            i += 1
        hunks.append(_build_hunk(header, body))
    return hunks
