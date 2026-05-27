"""Parse a raw unified diff into a structured model, and scaffold it as Markdown.

`gh pr diff` / `git diff` emit a raw unified diff that, viewed as Markdown, is
unreadable. This module first parses such input into a small, framework-free
model (`parse_diff` → `list[FileDiff]`). Two consumers render that model:

- the TUI swaps each ```diff fence emitted by `diff_to_markdown` for a
  delta-styled `DiffHunk` widget (see `mdview.diff_widget` / `mdview.diffview`);
- the non-TTY path renders the model directly with Rich.

`diff_to_markdown` keeps each file as a `## @ ` heading (so the TOC lists changed
files and `]`/`[` jump between them; the `@ ` prefix is the `/` search hook —
see `mdview.app`) but, unlike before, does **not** turn `@@` hunk headers into
`###` headings — the hunk body simply lives in a ```diff fence that the TUI
replaces. The transform is purely deterministic: same input always yields the
same output.
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
# Markdown inline characters that must be escaped inside heading text.
_MD_SPECIAL_RE = re.compile(r"([\\`*_\[\]<])")

_STATUS_SUFFIX = {
    "new file": " (new file)",
    "deleted": " (deleted)",
    "renamed": " (renamed)",
}


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


def _escape_md(text: str) -> str:
    """Backslash-escape characters that would trigger Markdown inline markup.

    Covers emphasis (`*` `_`), code (`` ` ``), links (`[` `]`) and raw HTML /
    autolinks (`<`) — e.g. keeps `__init__.py` from rendering "init" in bold.
    """
    return _MD_SPECIAL_RE.sub(r"\\\1", text)


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


def _max_backtick_run(text: str) -> int:
    return max((len(run) for run in re.findall(r"`+", text)), default=0)


def looks_like_diff(text: str) -> bool:
    """Heuristically decide whether *the whole input* is a unified diff.

    Front-anchored: the *first* non-empty line must itself start a diff. This
    avoids misclassifying ordinary Markdown that merely embeds a diff example
    (e.g. inside a ```diff fence) — such a document begins with prose/headings,
    not with `diff --git` or `--- `.
    """
    lines = _lines(text)
    first = next((line for line in lines if line.strip()), "")
    if first.startswith("diff --git "):
        return True
    # Plain unified diff (`diff -u`, a .patch): starts with `--- `, then `+++ `,
    # with at least one hunk header somewhere below.
    if first.startswith("--- "):
        has_plus = any(line.startswith("+++ ") for line in lines)
        has_hunk = any(_HUNK_RE.match(line) for line in lines)
        return has_plus and has_hunk
    return False


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


def parse_hunk_lines(code: str) -> Hunk:
    """Parse a standalone fence body (e.g. a ```diff block authored in Markdown).

    The body may or may not start with an `@@` header; everything else is a
    normal unified-diff body. Used for diff fences that are *not* part of a
    whole-document diff (so there is no `FileDiff` model to draw from).
    """
    lines = _lines(code)
    if lines and _HUNK_RE.match(lines[0]):
        return _build_hunk(lines[0], lines[1:])
    return _build_hunk("", lines)


def diff_to_markdown(files: list[FileDiff]) -> str:
    """Scaffold parsed *files* as Markdown the TUI can post-process.

    Each file becomes a `##` heading; each hunk becomes a single ```diff fence
    holding its raw text. The fence is a placeholder the TUI swaps for a
    delta-styled widget — and a readable fallback if it does not.

    The file heading is prefixed with `@ ` so the `/` search has a stable hook:
    its rendered text starts with `@ ` while a hunk header starts with `@@ `,
    so `^@ ` jumps between files and `@@` between hunks (see mdview.search).
    """
    blocks: list[str] = []
    for file in files:
        blocks.append(f"## @ {_escape_md(file.path)}{_STATUS_SUFFIX.get(file.status, '')}")
        if file.binary_note:
            blocks.append(_escape_md(file.binary_note))
        for hunk in file.hunks:
            fence = "`" * max(3, _max_backtick_run(hunk.raw) + 1)
            blocks.append(f"{fence}diff\n{hunk.raw}\n{fence}" if hunk.raw else f"{fence}diff\n{fence}")
    return "\n\n".join(blocks) + "\n"
