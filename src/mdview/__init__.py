"""Readable TUI markdown viewer."""

import logging

# `textual_image.widget` probes the terminal for its pixel cell size at *import
# time* (it calls `textual_image._terminal.get_cell_size()` from module scope, to
# fill a cache). On terminals that don't answer the `CSI 16 t` query — macOS
# Terminal.app, most SSH sessions — that probe times out after 0.1s and the
# library logs a WARNING *with a full traceback* (`exc_info=`) before falling
# back to VT340 cell sizes. mdview configures no logging, so that traceback would
# dump straight to the terminal on launch, looking like a crash when nothing is
# actually wrong (images still render, just via the fallback size).
#
# Quiet just that logger here — this module runs before any `mdview.*` submodule
# (and hence before `textual_image` is imported), so the level is in place by the
# time the probe runs. Only the benign fallback noise is suppressed; genuine
# errors (ERROR+) still surface.
logging.getLogger("textual_image._terminal").setLevel(logging.ERROR)
