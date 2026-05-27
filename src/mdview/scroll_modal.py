"""ModalScreen base that scrolls its *own* content with the app's movement keys.

A modal sits over the document. Without these bindings the app-level movement
keys (`j`/`k`, `d`/`u`, `f`/`b`, Space, …) bind only on the App, so pressing them
with a modal open scrolls the document *behind* it instead of the modal. A
subclass mixes this in by extending it and implementing `scroll_region()` to
name the `ScrollView`/`VerticalScroll` the keys should drive.

Two Textual facts this relies on:
- BINDINGS are collected only from `DOMNode` subclasses in the MRO, so this must
  be a real `ModalScreen` subclass — a plain mixin's BINDINGS are ignored.
- An unhandled key bubbles up the focus chain to the screen, so these fire even
  when a child (a focused `VerticalScroll`, the `Tree`, …) holds focus. A focused
  single-line `Input` does swallow the printable letters as text, so while
  typing in such a modal you scroll with the arrows / PageUp / PageDown (which
  `Input` ignores) — the letter keys resume scrolling once it loses focus.
"""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import ScrollableContainer
from textual.screen import ModalScreen


class ScrollableModalScreen(ModalScreen):
    # `msd_` (modal-scroll) action names so they never collide with a subclass's
    # own actions. Mirrors the main view's less-style keys (see app.BINDINGS).
    BINDINGS = [
        Binding("j,down", "msd_line_down", "Down", show=False),
        Binding("k,up", "msd_line_up", "Up", show=False),
        Binding("d,ctrl+d", "msd_half_down", "Half page down", show=False),
        Binding("u,ctrl+u", "msd_half_up", "Half page up", show=False),
        Binding("f,space,pagedown", "msd_page_down", "Page down", show=False),
        Binding("b,shift+space,pageup", "msd_page_up", "Page up", show=False),
        Binding("g,less_than_sign", "msd_top", "Top", show=False),
        Binding("G,greater_than_sign", "msd_bottom", "Bottom", show=False),
    ]

    def scroll_region(self) -> ScrollableContainer:
        """The container the movement keys scroll. Subclasses override."""
        raise NotImplementedError

    def action_msd_line_down(self) -> None:
        self.scroll_region().scroll_relative(y=1, animate=False)

    def action_msd_line_up(self) -> None:
        self.scroll_region().scroll_relative(y=-1, animate=False)

    def action_msd_half_down(self) -> None:
        region = self.scroll_region()
        region.scroll_relative(y=region.size.height // 2, animate=False)

    def action_msd_half_up(self) -> None:
        region = self.scroll_region()
        region.scroll_relative(y=-(region.size.height // 2), animate=False)

    def action_msd_page_down(self) -> None:
        region = self.scroll_region()
        region.scroll_relative(y=max(1, region.size.height - 1), animate=False)

    def action_msd_page_up(self) -> None:
        region = self.scroll_region()
        region.scroll_relative(y=-max(1, region.size.height - 1), animate=False)

    def action_msd_top(self) -> None:
        self.scroll_region().scroll_home(animate=False)

    def action_msd_bottom(self) -> None:
        self.scroll_region().scroll_end(animate=False)
