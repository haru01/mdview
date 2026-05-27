"""Click-to-zoom for rendered images (SVG diagrams).

``textual_image``'s ``Image`` can't be subclassed (its metaclass demands a
``Renderable``), so a ``ZoomableImage`` instead *wraps* an ``Image`` in a
clickable container. A click opens an ``ImageZoomScreen`` that shows the same
picture filling the screen. Kept apart from the app/modal so both reuse it.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual_image.widget import Image


class ImageZoomScreen(ModalScreen):
    """Full-screen overlay showing one image; click anywhere or press Esc to close."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    def __init__(self, image_path: Path) -> None:
        super().__init__()
        self._image_path = image_path

    def compose(self) -> ComposeResult:
        with Container(id="zoom-dialog"):
            yield Image(self._image_path, id="zoom-image")

    def on_click(self) -> None:
        self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()


class ZoomableImage(Container):
    """An image that opens a full-screen zoom view when clicked.

    The click lands on the inner ``Image`` and bubbles up to this container,
    which handles it — so the whole picture is one big click target.
    """

    # The container takes a definite width (100% of its parent) so the inner
    # image's `max-width: 100%` has something to resolve against; height tracks
    # the image. A `width: auto` container collapses to 0×0 here (circular with
    # the child's percentage width) and becomes unclickable.
    DEFAULT_CSS = """
    ZoomableImage {
        width: 100%;
        height: auto;
    }
    """

    def __init__(self, image_path: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self._image_path = image_path
        self.tooltip = "クリックで拡大"

    def compose(self) -> ComposeResult:
        yield Image(self._image_path, classes="mdview-image")

    def on_click(self) -> None:
        self.app.push_screen(ImageZoomScreen(self._image_path))
