"""Keyboard 'peek' preview for Obsidian-style wikilinks (the ``p`` key).

Two modals, the thin Textual wrappers over the pure helpers in ``wikilink.py``:

- :class:`WikiLinkPickerScreen` — pick a wikilink from the current document
  (``Input`` + ``OptionList``, fuzzy-filtered exactly like the commit browser).
  Mouse hover is deferred (unreliable over tmux/SSH); this is the reliable
  keyboard entry point. Dismisses the chosen ``(target, display)`` pair or None.
- :class:`WikiPeekScreen` — a scrollable preview of the chosen note rendered as
  bare Markdown (reusing :class:`ScrollableModalScreen`, as ``SelectionViewScreen``
  does, so it inherits the main view's colours). ``o``/``Enter`` jumps to the
  note; ``Esc``/``q`` just closes the preview.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Markdown, OptionList
from textual.widgets.option_list import Option

from mdview.quickopen import fuzzy_filter
from mdview.scroll_modal import ScrollableModalScreen


class WikiLinkPickerScreen(ModalScreen):
    """Pick a wikilink. Dismisses the chosen ``(target, display)`` or None.

    Mirrors ``CommitLogScreen``: a plain modal that delegates list movement to
    the ``OptionList`` so the arrows work while the ``Input`` keeps focus.
    """

    BINDINGS = [
        ("escape", "dismiss(None)", "Close"),
        ("down,ctrl+n", "cursor_down", "Down"),
        ("up,ctrl+p", "cursor_up", "Up"),
    ]

    def __init__(self, links: list[tuple[str, str]]) -> None:
        super().__init__()
        self._links = links  # (target, display) pairs
        self._ranked: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="wiki-peek-dialog") as dialog:
            dialog.border_title = "ウィキリンク peek  (p)"
            yield Input(
                placeholder="リンク名で絞り込み… (Enter でプレビュー, Esc で閉じる)",
                id="wiki-peek-input",
            )
            yield OptionList(id="wiki-peek-list")

    def on_mount(self) -> None:
        self._repopulate("")
        self.query_one("#wiki-peek-input", Input).focus()

    def _repopulate(self, query: str) -> None:
        ranked = fuzzy_filter(query, self._links, key=_match_text)
        self._ranked = [link for link, _ in ranked]
        option_list = self.query_one("#wiki-peek-list", OptionList)
        option_list.clear_options()
        option_list.add_options(_render_link(link) for link in self._ranked)
        if self._ranked:
            option_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._repopulate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._dismiss_with(self.query_one("#wiki-peek-list", OptionList).highlighted)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._dismiss_with(event.option_index)

    def action_cursor_down(self) -> None:
        self.query_one("#wiki-peek-list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#wiki-peek-list", OptionList).action_cursor_up()

    def _dismiss_with(self, index: int | None) -> None:
        if index is None or not (0 <= index < len(self._ranked)):
            self.dismiss(None)
            return
        self.dismiss(self._ranked[index])


def _match_text(link: tuple[str, str]) -> str:
    """The text a query filters against: display text + target name."""
    target, display = link
    return f"{display} {target}"


def _render_link(link: tuple[str, str]) -> Option:
    """A row: the display text in accent, plus the raw ``[[target]]`` (muted)
    when it differs from the display."""
    target, display = link
    rendered = Text(display, style="bold #e8a87c")
    if display != target:
        rendered.append(f"  [[{target}]]", style="#888888")
    return Option(rendered)


class WikiPeekScreen(ScrollableModalScreen):
    """Scrollable preview of a note. ``o``/``Enter`` jumps; ``Esc``/``q`` closes.

    Dismisses ``True`` to tell the app to navigate to the note, else ``False``.
    Renders the note as a bare ``Markdown`` widget so it shares the main view's
    colours/spacing (theme.css styles ``Markdown``/``MarkdownBlock`` by type).
    """

    BINDINGS = [
        ("escape", "dismiss(False)", "Close"),
        ("q", "dismiss(False)", "Close"),
        ("o,enter", "jump", "Open"),
    ]

    def __init__(self, title: str, text: str) -> None:
        super().__init__()
        self._title = title
        self._text = text

    def compose(self) -> ComposeResult:
        with Container(id="wiki-peek-view-dialog") as dialog:
            dialog.border_title = f"{self._title}  (o で開く)"
            with VerticalScroll(id="wiki-peek-view-body"):
                yield Markdown(self._text)

    def scroll_region(self) -> ScrollableContainer:
        return self.query_one("#wiki-peek-view-body", VerticalScroll)

    def action_jump(self) -> None:
        self.dismiss(True)
