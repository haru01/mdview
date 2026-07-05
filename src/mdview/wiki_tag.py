"""The wiki candidate picker modal (tag search / ambiguous ``[[wikilink]]``).

A thin Textual wrapper mirroring ``quick_open.py``: an input box whose every
keystroke fuzzily re-ranks a fixed list of candidate files into an
``OptionList``, Enter dismisses with the chosen ``Path``. The app pushes it with
the files carrying a clicked tag, or the several files a ``[[name]]`` could
resolve to, and routes the dismissed path through its normal navigation.
"""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

from mdview.quickopen import fuzzy_filter

_MAX_RESULTS = 200


class WikiPickScreen(ModalScreen):
    """Fuzzy picker over a list of candidate files. Dismisses with a `Path` or None."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("down,ctrl+n", "cursor_down", "Down"),
        ("up,ctrl+p", "cursor_up", "Up"),
    ]

    def __init__(self, paths: list[Path], root: Path, title: str) -> None:
        super().__init__()
        self._paths = paths
        self._root = Path(root)
        self._title = title
        # Root-relative labels for display/fuzzy matching, paired to their paths.
        self._labels = [self._rel(p) for p in paths]
        self._ranked: list[tuple[int, list[int]]] = []

    def _rel(self, path: Path) -> str:
        try:
            return path.relative_to(self._root).as_posix()
        except ValueError:
            return path.name

    def compose(self) -> ComposeResult:
        with Vertical(id="wiki-pick-dialog") as dialog:
            dialog.border_title = self._title
            yield Input(
                placeholder="絞り込み… (Enter で開く, Esc で閉じる)",
                id="wiki-pick-input",
            )
            yield OptionList(id="wiki-pick-list")

    def on_mount(self) -> None:
        self._repopulate("")
        self.query_one("#wiki-pick-input", Input).focus()

    def _repopulate(self, query: str) -> None:
        indexed = list(enumerate(self._labels))
        ranked = fuzzy_filter(query, indexed, key=lambda pair: pair[1])[:_MAX_RESULTS]
        self._ranked = [((idx), indices) for (idx, _label), indices in ranked]
        option_list = self.query_one("#wiki-pick-list", OptionList)
        option_list.clear_options()
        option_list.add_options(
            Option(_render_label(self._labels[idx], indices))
            for idx, indices in self._ranked
        )
        if self._ranked:
            option_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._repopulate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._pick(self.query_one("#wiki-pick-list", OptionList).highlighted)

    def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        self._pick(event.option_index)

    def action_cursor_down(self) -> None:
        self.query_one("#wiki-pick-list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#wiki-pick-list", OptionList).action_cursor_up()

    def _pick(self, index: int | None) -> None:
        if index is None or not (0 <= index < len(self._ranked)):
            self.dismiss(None)
            return
        self.dismiss(self._paths[self._ranked[index][0]])


def _render_label(text: str, indices: list[int]) -> Text:
    """The candidate path with its fuzzy-matched characters highlighted."""
    rendered = Text(text)
    for i in indices:
        rendered.stylize("bold #e8a87c", i, i + 1)
    return rendered
