"""The project-wide grep finder modal (``Ctrl+G`` / ``:grep``).

A thin Textual wrapper over ``projectgrep.py``: an input box whose every keystroke
re-runs `grep_files` across the viewable files under a root and lists the matched
lines (``path:line: text``, matched substrings highlighted) in an ``OptionList``.
Enter dismisses with a `GrepResult` (the chosen hit + the query), which the app
turns into a navigation + an in-document search. Mirrors ``quick_open.py``'s
pattern — a plain ``ModalScreen`` that delegates list movement to the widget so the
keys work while the input keeps focus.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from mdview.projectgrep import GrepHit, grep_files

# Cap on options rendered per keystroke (grep itself caps total hits higher);
# rebuilding a huge OptionList on each character would stutter.
_MAX_RESULTS = 200


@dataclass(frozen=True)
class GrepResult:
    """The picked grep hit plus the query that found it, so the app can both open
    the file and activate the same search in it."""

    hit: GrepHit
    query: str


class ProjectGrepScreen(ModalScreen):
    """Cross-file grep picker. Dismisses with a `GrepResult`, or None."""

    # The Input keeps focus (so typing filters); these movement/confirm keys are
    # bound on the screen and delegate to the OptionList, like QuickOpenScreen.
    BINDINGS = [
        ("escape", "dismiss(None)", "Close"),
        ("down,ctrl+n", "cursor_down", "Down"),
        ("up,ctrl+p", "cursor_up", "Up"),
    ]

    def __init__(self, root: Path, files: list[Path]) -> None:
        super().__init__()
        self._root = root
        # The viewable files under root, enumerated once by the app so each
        # keystroke re-searches without re-walking the tree.
        self._files = files
        self._query = ""
        # The hits currently shown, in display order; the highlighted index maps
        # into this slice.
        self._hits: list[GrepHit] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="project-grep-dialog") as dialog:
            dialog.border_title = "プロジェクト検索  (Ctrl+G / :grep)"
            yield Input(
                placeholder="検索語（正規表現可）… (Enter で開く, Esc で閉じる)",
                id="project-grep-input",
            )
            yield OptionList(id="project-grep-list")
            yield Static("", id="project-grep-status")

    def on_mount(self) -> None:
        self.query_one("#project-grep-input", Input).focus()

    def _repopulate(self, query: str) -> None:
        """Re-run grep for *query* and rebuild the option list."""
        self._query = query
        hits, truncated = grep_files(self._root, query, files=self._files)
        self._hits = hits[:_MAX_RESULTS]
        option_list = self.query_one("#project-grep-list", OptionList)
        option_list.clear_options()
        option_list.add_options(_render_hit(hit) for hit in self._hits)
        if self._hits:
            option_list.highlighted = 0
        self._update_status(len(hits), truncated, query)

    def _update_status(self, total: int, truncated: bool, query: str) -> None:
        status = self.query_one("#project-grep-status", Static)
        if not query:
            status.update("")
            return
        if total == 0:
            status.update("一致なし")
            return
        shown = min(total, _MAX_RESULTS)
        more = f"（先頭 {shown} 件を表示" if total > _MAX_RESULTS else f"（{total} 件"
        if truncated:
            more += "・打ち切り"
        status.update(more + "）")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._repopulate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._open_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        # A mouse click on a row selects it; open that one.
        self._dismiss_with(event.option_index)

    def action_cursor_down(self) -> None:
        self.query_one("#project-grep-list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#project-grep-list", OptionList).action_cursor_up()

    def _open_highlighted(self) -> None:
        self._dismiss_with(
            self.query_one("#project-grep-list", OptionList).highlighted
        )

    def _dismiss_with(self, index: int | None) -> None:
        if index is None or not (0 <= index < len(self._hits)):
            self.dismiss(None)
            return
        self.dismiss(GrepResult(self._hits[index], self._query))


def _render_hit(hit: GrepHit) -> Option:
    """A row: a muted ``path:line:`` location prefix, then the matched line with
    its matched substrings highlighted (bold orange, as the quick-open finder)."""
    prefix = f"{hit.rel}:{hit.line_no}: "
    rendered = Text(prefix, style="#888888")
    body = Text(hit.line.strip("\n"))
    # The line was stripped of its newline already; spans index the raw line, so
    # they line up with `hit.line` here.
    for start, end in hit.spans:
        body.stylize("bold #e8a87c", start, end)
    rendered.append_text(body)
    return Option(rendered)
