"""The commit-log browser modal (``--log`` / ``:log``).

A thin Textual wrapper over ``gitlog.py``: an input box that fuzzy-filters a list
of commits (reusing ``quickopen.fuzzy_filter``) in an ``OptionList``. Enter
dismisses with the chosen `Commit`, which the app turns into a `git show` diff
rendered in the transient diff view. Mirrors ``quick_open.py``'s pattern — a plain
``ModalScreen`` that delegates list movement to the widget so the keys work while
the input keeps focus.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

from mdview.gitlog import Commit
from mdview.palette import ACCENT_BRIGHT, TEXT_MUTED
from mdview.quickopen import fuzzy_filter

_MAX_RESULTS = 200


class CommitLogScreen(ModalScreen):
    """Commit picker. Dismisses with the chosen `Commit`, or None."""

    BINDINGS = [
        ("escape", "dismiss(None)", "Close"),
        ("down,ctrl+n", "cursor_down", "Down"),
        ("up,ctrl+p", "cursor_up", "Up"),
    ]

    def __init__(self, commits: list[Commit]) -> None:
        super().__init__()
        self._commits = commits
        # The ranked slice currently shown; the highlighted index maps into it.
        self._ranked: list[Commit] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="commit-log-dialog") as dialog:
            dialog.border_title = "コミット履歴  (:log)"
            yield Input(
                placeholder="メッセージ/作者で絞り込み… (Enter で diff を開く, Esc で閉じる)",
                id="commit-log-input",
            )
            yield OptionList(id="commit-log-list")

    def on_mount(self) -> None:
        self._repopulate("")
        self.query_one("#commit-log-input", Input).focus()

    def _repopulate(self, query: str) -> None:
        """Fuzzy-filter the commits against *query* and rebuild the option list."""
        ranked = fuzzy_filter(query, self._commits, key=_match_text)[:_MAX_RESULTS]
        self._ranked = [commit for commit, _ in ranked]
        option_list = self.query_one("#commit-log-list", OptionList)
        option_list.clear_options()
        option_list.add_options(_render_commit(commit) for commit in self._ranked)
        if self._ranked:
            option_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._repopulate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._open_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._dismiss_with(event.option_index)

    def action_cursor_down(self) -> None:
        self.query_one("#commit-log-list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#commit-log-list", OptionList).action_cursor_up()

    def _open_highlighted(self) -> None:
        self._dismiss_with(self.query_one("#commit-log-list", OptionList).highlighted)

    def _dismiss_with(self, index: int | None) -> None:
        if index is None or not (0 <= index < len(self._ranked)):
            self.dismiss(None)
            return
        self.dismiss(self._ranked[index])


def _match_text(commit: Commit) -> str:
    """The text a query filters against: short hash + subject + author."""
    return f"{commit.short} {commit.subject} {commit.author}"


def _render_commit(commit: Commit) -> Option:
    """A row: ``shorthash  subject  (author, date)`` with the hash in accent and
    the author/date muted, matching the finder look elsewhere."""
    rendered = Text(commit.short, style=f"bold {ACCENT_BRIGHT}")
    rendered.append(f"  {commit.subject}  ")
    rendered.append(f"({commit.author}, {commit.date})", style=TEXT_MUTED)
    return Option(rendered)
