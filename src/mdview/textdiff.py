"""Generate a unified diff from two in-memory strings (for the AI edit preview).

Kept framework-free (like diff.py / search.py / command.py) so it is unit-
testable without Textual. It is the head of the edit-preview stack: the AI edit
loop turns a scope's original text and Claude's edited text into a unified-diff
string here, which `diff.parse_hunks` → `diffview.render_hunk` then render in
`diff_preview.DiffPreviewScreen` for the user to accept or reject.
"""

from __future__ import annotations

import difflib


def build_unified_diff(original: str, edited: str, *, label: str = "section") -> str:
    """Return a unified diff transforming *original* into *edited*.

    Returns ``""`` when the two are identical — the caller's no-op signal (don't
    open an empty preview). The ``label`` only names the ``---``/``+++`` header
    lines, which the preview skips (it renders hunks), so it is cosmetic. Lines
    are split keeping
    their newlines so difflib emits a correct hunk even when an input lacks a
    trailing newline.
    """
    if original == edited:
        return ""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        edited.splitlines(keepends=True),
        fromfile=f"{label} (original)",
        tofile=f"{label} (edited)",
    )
    return "".join(diff)
