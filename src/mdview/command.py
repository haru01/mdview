"""`:` command-line parsing for the TUI.

Kept framework-free (like search.py / diff.py) so it is unit-testable without a
Textual app: `parse_command` maps the text typed after the `:` prompt to a
canonical command name the app dispatches. Unknown or empty input returns None
so the app can hide the bar silently (empty) or warn (unknown — the caller
distinguishes by also checking whether the raw text was blank).
"""

from __future__ import annotations

# Accepted spellings → canonical command. Mirrors less/vim: `:q`/`:quit` quit,
# `:h`/`:help` open help. The AI edit loop adds `:w` (write the buffer), `:q!`
# (force quit, discarding unsaved edits), `:wq` (write then quit), and `:undo`
# (revert the last applied edit). `:e`/`:edit`/`:open`/`:o` open the quick-open
# fuzzy finder (also bound to Ctrl+P).
_COMMANDS = {
    "q": "quit",
    "quit": "quit",
    "q!": "force_quit",
    "quit!": "force_quit",
    "w": "write",
    "write": "write",
    "wq": "write_quit",
    "x": "write_quit",
    "undo": "undo",
    "u": "undo",
    "h": "help",
    "help": "help",
    "e": "open",
    "edit": "open",
    "open": "open",
    "o": "open",
}


def parse_command(raw: str) -> str | None:
    """Return the canonical command for the text typed after `:`.

    `raw` is the input value without the leading `:`. Surrounding whitespace is
    ignored. Returns ``"quit"`` / ``"help"`` for a known command, or ``None``
    for empty or unrecognised input.
    """
    return _COMMANDS.get(raw.strip().lower())
