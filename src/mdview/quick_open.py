"""The quick-open fuzzy finder modal (``Ctrl+P`` / ``:e``).

A thin Textual wrapper over ``quickopen.py``: an input box whose every keystroke
re-ranks the entries (viewable files, plus git/gh diff sources in a repo) with an
fzf-style subsequence match into an ``OptionList``, and Enter dismisses with the
chosen entry's payload (an absolute file path or a ``DiffSource``). The app routes
that to navigation or a captured-diff view. Mirrors ``toc.py``'s pattern — a plain
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

from mdview.quickopen import QuickOpenEntry, fuzzy_filter

# Cap on options rendered per keystroke: ranking scans every entry, but rebuilding
# a huge OptionList on each character would stutter. The best matches are shown.
_MAX_RESULTS = 200


class QuickOpenScreen(ModalScreen):
    """Fuzzy picker. Dismisses with the chosen entry's payload, or None."""

    # The Input keeps focus (so typing filters); these movement/confirm keys are
    # bound on the screen and delegate to the OptionList, like TocScreen does for
    # its Tree. A single-line Input ignores up/down, so they reach us here.
    BINDINGS = [
        ("escape", "dismiss(None)", "Close"),
        ("down,ctrl+n", "cursor_down", "Down"),
        ("up,ctrl+p", "cursor_up", "Up"),
    ]

    def __init__(self, entries: list[QuickOpenEntry]) -> None:
        super().__init__()
        self._entries = entries
        # Entries in current display order; the highlighted index maps here.
        self._current: list[QuickOpenEntry] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="quick-open-dialog") as dialog:
            dialog.border_title = "ファイルを開く"
            yield Input(placeholder="ファイル名を入力… (Enter で開く, Esc で閉じる)", id="quick-open-input")
            yield OptionList(id="quick-open-list")

    def on_mount(self) -> None:
        self._repopulate("")
        self.query_one("#quick-open-input", Input).focus()

    def _repopulate(self, query: str) -> None:
        """Re-rank the entries against *query* and rebuild the option list."""
        ranked = fuzzy_filter(query, self._entries, key=lambda e: e.label)
        self._current = [item for item, _ in ranked[:_MAX_RESULTS]]
        option_list = self.query_one("#quick-open-list", OptionList)
        option_list.clear_options()
        option_list.add_options(
            Option(_render_path(item.label, indices))
            for item, indices in ranked[:_MAX_RESULTS]
        )
        if self._current:
            option_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._repopulate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._open_highlighted()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        # A mouse click on a row selects it; open that one.
        self._dismiss_with(event.option_index)

    def action_cursor_down(self) -> None:
        self.query_one("#quick-open-list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#quick-open-list", OptionList).action_cursor_up()

    def _open_highlighted(self) -> None:
        self._dismiss_with(self.query_one("#quick-open-list", OptionList).highlighted)

    def _dismiss_with(self, index: int | None) -> None:
        if index is None or not (0 <= index < len(self._current)):
            self.dismiss(None)
            return
        self.dismiss(self._current[index].payload)


def _render_path(text: str, indices: list[int]) -> Text:
    """The path with its fuzzy-matched characters highlighted (bold orange)."""
    rendered = Text(text)
    for i in indices:
        rendered.stylize("bold #e8a87c", i, i + 1)
    return rendered
