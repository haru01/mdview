"""Textual wrapper that renders one diff hunk in a delta-like style.

Thin by design (the rendering lives in the pure `mdview.diffview`): a `Static`
whose content is the delta-styled `Text`, with `get_selection` overridden so the
*displayed* text (line-number gutter included) and the *selectable* text differ.
Selecting a hunk — for copy or for Ask AI — yields a valid unified diff
(`+`/`-` markers kept, no gutter), which is what `hunk_plain_text` returns.

It lives in its own module so `mdview.selection` can treat `DiffHunk` as an
atomic block without importing `mdview.app` (which would be circular).
"""

from __future__ import annotations

from textual.selection import Selection
from textual.widgets import Static

from mdview.diff import Hunk
from mdview.diffview import hunk_plain_text, render_hunk


class DiffHunk(Static):
    """A delta-styled, text-selectable rendering of a single diff hunk."""

    def __init__(self, hunk: Hunk, *, file_path: str | None = None) -> None:
        self._hunk = hunk
        self._file_path = file_path
        self._plain = hunk_plain_text(hunk)  # selectable text (clean diff)
        super().__init__(render_hunk(hunk, file_path=file_path))  # displayed text

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        # Extract from the clean diff, not the gutter-laden display. For a
        # whole-widget selection (SELECT_ALL) this returns the entire hunk.
        return selection.extract(self._plain), "\n"
