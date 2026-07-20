"""Package-init / CLI startup behaviour."""

from __future__ import annotations

import logging


def test_textual_image_terminal_logger_quieted() -> None:
    """Importing mdview raises the noisy ``textual_image._terminal`` logger above
    WARNING.

    That logger emits a "Failed to get cell size … assuming VT340 sizes" warning
    *with a traceback* (``exc_info``) at ``textual_image.widget`` import time on
    any terminal that doesn't answer the pixel cell-size query (e.g. macOS
    Terminal.app). Since mdview configures no logging, that traceback would dump
    straight to the terminal on launch. We quiet it in ``mdview/__init__`` — the
    VT340 fallback itself is unaffected, only the noise is gone.
    """
    import mdview  # noqa: F401  (runs mdview/__init__.py)

    logger = logging.getLogger("textual_image._terminal")
    assert logger.getEffectiveLevel() >= logging.ERROR
