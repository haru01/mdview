"""Popup (centered modal) table of contents.

The docked sidebar TOC truncates long headings — e.g. a piped diff's file paths
and ``@@`` hunk headers — to its narrow width. This shows the same TOC in a wide
centered modal instead, so headings stay readable.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import MarkdownViewer, Tree
from textual.widgets._markdown import Markdown, MarkdownBlock, MarkdownTableOfContents


class TocScreen(ModalScreen):
    """A modal that shows the document's table of contents in a wide popup."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("t", "dismiss", "Close"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
    ]

    def __init__(self, viewer: MarkdownViewer, toc_data: object) -> None:
        super().__init__()
        self._viewer = viewer
        self._toc_data = toc_data

    def compose(self) -> ComposeResult:
        with Container(id="toc-dialog") as dialog:
            dialog.border_title = "目次"
            yield MarkdownTableOfContents(self._viewer.document)

    def on_mount(self) -> None:
        # Feed the modal's TOC the data Textual built for the (hidden) sidebar
        # one; setting the reactive rebuilds the tree.
        self.query_one(MarkdownTableOfContents).table_of_contents = self._toc_data

    def on_markdown_table_of_contents_selected(
        self, message: Markdown.TableOfContentsSelected
    ) -> None:
        # The modal's TOC isn't a child of the viewer, so the viewer's own
        # handler never fires — we scroll the document ourselves and close.
        message.stop()
        try:
            block = self._viewer.query_one(f"#{message.block_id}", MarkdownBlock)
        except NoMatches:
            self.dismiss()
            return
        self._viewer.scroll_to_widget(block, top=True)
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()

    def action_cursor_down(self) -> None:
        self.query_one(Tree).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(Tree).action_cursor_up()
