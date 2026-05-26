"""Mechanically turn a raw unified diff into structured Markdown.

`gh pr diff` / `git diff` emit a raw unified diff that, viewed as Markdown,
is unreadable: headers and `+`/`-` lines get misparsed and nothing is coloured.
This module rewrites such input into Markdown where each file becomes an `##`
heading and each `@@` hunk a `### @@ ...` heading, with the hunk body in a
```diff fenced block. That makes the diff readable (the fence is colour-
highlighted downstream) and navigable (`n`/`p` jump between the headings).

The transform is purely deterministic string processing — no LLM, no external
process. Same input always yields the same output.
"""

from __future__ import annotations

import re

# A hunk header: `@@ -12,3 +12,4 @@ optional context`
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")
# Split a hunk header into its `@@ ... @@` range part and the trailing context.
_HUNK_SPLIT_RE = re.compile(r"^(@@ .*? @@)(.*)$")
# `diff --git a/<path> b/<path>` — greedy, good enough for paths without spaces.
_GIT_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")
# Markdown inline characters that must be escaped inside heading text.
_MD_SPECIAL_RE = re.compile(r"([\\`*_\[\]<])")


def _escape_md(text: str) -> str:
    """Backslash-escape characters that would trigger Markdown inline markup.

    Covers emphasis (`*` `_`), code (`` ` ``), links (`[` `]`) and raw HTML /
    autolinks (`<`) — e.g. keeps `__init__.py` from rendering "init" in bold and
    `List[int]` / `<tag>` in a hunk's context from being mangled.
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


def diff_to_markdown(text: str) -> str:
    """Rewrite a unified diff into structured, navigable Markdown."""
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

    blocks: list[str] = []
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
        # (which is itself a file-start marker) from ending the scan on entry —
        # otherwise `i` would never advance and the parser would spin forever.
        while (
            i < n
            and not _HUNK_RE.match(lines[i])
            and not (i > section_start and is_file_start(i))
        ):
            line = lines[i]
            if line.startswith("new file mode"):
                status = " (new file)"
            elif line.startswith("deleted file mode"):
                status = " (deleted)"
            elif line.startswith(("rename from", "rename to", "copy to")):
                status = " (renamed)"
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

        display = (path_a if status == " (deleted)" else path_b) or path_b or path_a or "(unknown)"
        blocks.append(f"## {_escape_md(display)}{status}")
        if binary_note:
            blocks.append(_escape_md(binary_note))

        # Hunks.
        while i < n and _HUNK_RE.match(lines[i]):
            header = lines[i]
            i += 1
            body: list[str] = []
            while i < n and not _HUNK_RE.match(lines[i]) and not is_file_start(i):
                body.append(lines[i])
                i += 1

            split = _HUNK_SPLIT_RE.match(header)
            heading = split.group(1) + _escape_md(split.group(2)) if split else _escape_md(header)
            blocks.append(f"### {heading}")

            body_text = "\n".join(body)
            fence = "`" * max(3, _max_backtick_run(body_text) + 1)
            if body_text:
                blocks.append(f"{fence}diff\n{body_text}\n{fence}")
            else:
                blocks.append(f"{fence}diff\n{fence}")

        # Skip any stray lines before the next file boundary (malformed input).
        while i < n and not is_file_start(i) and not _HUNK_RE.match(lines[i]):
            i += 1

        # Defense in depth: never spin on a line that no clause above consumed.
        if i == section_start:
            i += 1

    return "\n\n".join(blocks) + "\n"


def maybe_diff_to_markdown(text: str) -> str:
    """Transform *text* if it looks like a diff, otherwise return it unchanged."""
    return diff_to_markdown(text) if looks_like_diff(text) else text
