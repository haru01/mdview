"""Parse a raw unified diff into a small, framework-free model.

The sole consumer is the AI edit preview: `textdiff.build_unified_diff` turns
the original and edited text into a unified diff, `parse_diff` parses it back
into `list[FileDiff]`, and `mdview.diffview.render_hunk` draws each hunk in the
delta style inside `mdview.diff_preview.DiffPreviewScreen`. The parse is purely
deterministic: same input always yields the same output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A hunk header: `@@ -12,3 +12,4 @@ optional context`
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
# Capture the old/new start line numbers from a hunk header.
_HUNK_START_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
# `diff --git a/<path> b/<path>` — greedy, good enough for paths without spaces.
_GIT_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass(frozen=True)
class DiffLine:
    """One body line of a hunk, classified and line-numbered."""

    kind: str  # "context" | "add" | "del"
    old_no: int | None
    new_no: int | None
    text: str  # the line content with its leading +/-/space marker stripped


@dataclass
class Hunk:
    """A single `@@ … @@` hunk: its header, body lines, and clean diff text."""

    header: str  # the full `@@ -.. +.. @@ context` line ("" if unknown)
    old_start: int
    new_start: int
    lines: list[DiffLine] = field(default_factory=list)
    raw: str = ""  # header + body as a valid unified diff (for selection / AI)


@dataclass
class FileDiff:
    """All hunks for one file, plus its path and status."""

    path: str
    status: str = ""  # "" | "new file" | "deleted" | "renamed"
    binary_note: str = ""
    hunks: list[Hunk] = field(default_factory=list)


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


def _strip_ab(path: str) -> str:
    """Normalise a `--- `/`+++ ` path: drop a trailing tab+timestamp and `a/`,`b/`."""
    path = path.split("\t", 1)[0].rstrip()
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def _build_hunk(header: str, body: list[str]) -> Hunk:
    """Classify *body* lines against *header*, numbering old/new sides."""
    match = _HUNK_START_RE.match(header)
    old_no, new_no = (int(match.group(1)), int(match.group(2))) if match else (1, 1)
    lines: list[DiffLine] = []
    for line in body:
        marker = line[:1]
        if marker == "+":
            lines.append(DiffLine("add", None, new_no, line[1:]))
            new_no += 1
        elif marker == "-":
            lines.append(DiffLine("del", old_no, None, line[1:]))
            old_no += 1
        elif marker == "\\":
            # "\ No newline at end of file" — metadata, not a numbered line.
            lines.append(DiffLine("context", None, None, line))
        else:  # " " context, or a bare blank line
            text = line[1:] if marker == " " else line
            lines.append(DiffLine("context", old_no, new_no, text))
            old_no += 1
            new_no += 1
    raw = "\n".join([header, *body]) if header else "\n".join(body)
    start = _HUNK_START_RE.match(header)
    return Hunk(
        header=header,
        old_start=int(start.group(1)) if start else 1,
        new_start=int(start.group(2)) if start else 1,
        lines=lines,
        raw=raw,
    )


def parse_diff(text: str) -> list[FileDiff]:
    """Parse a unified diff into a list of `FileDiff`."""
    lines = _lines(text)
    n = len(lines)
    has_git = any(line.startswith("diff --git ") for line in lines)

    def is_file_start(idx: int) -> bool:
        line = lines[idx]
        if line.startswith("diff --git "):
            return True
        # Plain diffs (no `diff --git`): a `--- ` followed by `+++ ` starts a file.
        if not has_git and line.startswith("--- "):
            return idx + 1 < n and lines[idx + 1].startswith("+++ ")
        return False

    files: list[FileDiff] = []
    i = 0
    while i < n and not is_file_start(i):  # skip any preamble
        i += 1

    while i < n:
        section_start = i
        path_a = path_b = None
        status = ""
        binary_note = ""

        if lines[i].startswith("diff --git "):
            match = _GIT_RE.match(lines[i])
            if match:
                path_a, path_b = match.group(1), match.group(2)
            i += 1

        # File header lines, up to the first hunk or the *next* file. The
        # `i > section_start` guard keeps a plain diff's own leading `--- ` line
        # (itself a file-start marker) from ending the scan on entry.
        while (
            i < n
            and not _HUNK_RE.match(lines[i])
            and not (i > section_start and is_file_start(i))
        ):
            line = lines[i]
            if line.startswith("new file mode"):
                status = "new file"
            elif line.startswith("deleted file mode"):
                status = "deleted"
            elif line.startswith(("rename from", "rename to", "copy to")):
                status = "renamed"
            elif line.startswith("--- "):
                stripped = _strip_ab(line[4:])
                if stripped != "/dev/null":
                    path_a = stripped
            elif line.startswith("+++ "):
                stripped = _strip_ab(line[4:])
                if stripped != "/dev/null":
                    path_b = stripped
            elif line.startswith("Binary files") and "differ" in line:
                binary_note = line.strip()
            i += 1

        display = (path_a if status == "deleted" else path_b) or path_b or path_a or "(unknown)"
        file = FileDiff(path=display, status=status, binary_note=binary_note)

        while i < n and _HUNK_RE.match(lines[i]):
            header = lines[i]
            i += 1
            body: list[str] = []
            while i < n and not _HUNK_RE.match(lines[i]) and not is_file_start(i):
                body.append(lines[i])
                i += 1
            file.hunks.append(_build_hunk(header, body))

        files.append(file)

        # Skip any stray lines before the next file boundary (malformed input).
        while i < n and not is_file_start(i) and not _HUNK_RE.match(lines[i]):
            i += 1

        # Defense in depth: never spin on a line that no clause above consumed.
        if i == section_start:
            i += 1

    return files


