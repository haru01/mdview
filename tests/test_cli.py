"""Package-init / CLI startup behaviour."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest


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


def _run_main(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    from mdview import cli

    monkeypatch.setattr("sys.argv", ["mdview", *argv])
    cli.main()


@pytest.mark.parametrize("name", ["change.diff", "change.patch", "change.DIFF"])
def test_diff_files_are_rejected(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """`.diff`/`.patch` are not a document type the viewer renders, so naming one
    exits with an error instead of dumping a wall of plain text."""
    path = tmp_path / name
    path.write_text("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _run_main([str(path)], monkeypatch)

    assert exc.value.code == 1
    assert "diff files are not supported" in capsys.readouterr().err
