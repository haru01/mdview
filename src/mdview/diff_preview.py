"""Modal previewing an AI edit as a delta-style diff before it is applied.

The AI edit loop never overwrites the buffer blindly: Claude's edited text is
diffed against the original scope and shown here in the same delta look as the
diff viewer, reusing the pure stack (`textdiff.build_unified_diff` →
`diff.parse_diff` → `diffview.render_hunk`). `y` accepts (dismiss True);
`n`/`Esc`/`q` reject (dismiss False). The caller owns the buffer update — this
screen only shows the change and resolves the decision.
"""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer, VerticalScroll
from textual.widgets import Static

from mdview.diff import parse_diff
from mdview.diffview import render_hunk
from mdview.scroll_modal import ScrollableModalScreen
from mdview.textdiff import build_unified_diff


class DiffPreviewScreen(ScrollableModalScreen):
    # y/n decide; Esc/q also reject. Movement keys are inherited (it can scroll a
    # tall diff). `n`/`y`/`q`/`escape` are free in the base's key map.
    BINDINGS = [
        ("y", "accept", "適用"),
        ("n", "reject", "取消"),
        ("escape", "reject", "取消"),
        ("q", "reject", "取消"),
    ]

    def __init__(
        self,
        original: str,
        edited: str,
        *,
        label: str = "section",
        file_path: str | None = None,
    ) -> None:
        super().__init__()
        self._original = original
        self._edited = edited
        self._label = label
        self._file_path = file_path

    def _render_preview(self) -> RenderableType:
        diff = build_unified_diff(self._original, self._edited, label=self._label)
        parts: list[RenderableType] = []
        for file in parse_diff(diff):
            for hunk in file.hunks:
                parts.append(render_hunk(hunk, file_path=self._file_path))
                parts.append(Text())  # blank line between hunks
        return Group(*parts) if parts else Text("(変更なし)")

    def compose(self) -> ComposeResult:
        with Container(id="diff-preview-dialog") as dialog:
            dialog.border_title = f"編集プレビュー — {self._label}"
            with VerticalScroll(id="diff-preview-body"):
                yield Static(self._render_preview(), id="diff-preview-content")
            yield Static("[b]y[/b] 適用    [b]n[/b] / Esc 取消", id="diff-preview-help")

    def scroll_region(self) -> ScrollableContainer:
        return self.query_one("#diff-preview-body", VerticalScroll)

    def action_accept(self) -> None:
        self.dismiss(True)

    def action_reject(self) -> None:
        self.dismiss(False)
