"""`:` command-line parsing for the TUI.

Kept framework-free (like search.py / diff.py) so it is unit-testable without a
Textual app: `parse_command` maps the text typed after the `:` prompt to a
canonical command name the app dispatches. Unknown or empty input returns None
so the app can hide the bar silently (empty) or warn (unknown — the caller
distinguishes by also checking whether the raw text was blank).
"""

from __future__ import annotations

# Accepted spellings → canonical command. Mirrors less/vim: `:q`/`:quit` quit,
# `:h`/`:help` open help.
_COMMANDS = {
    "q": "quit",
    "quit": "quit",
    "h": "help",
    "help": "help",
}


def parse_command(raw: str) -> str | None:
    """Return the canonical command for the text typed after `:`.

    `raw` is the input value without the leading `:`. Surrounding whitespace is
    ignored. Returns ``"quit"`` / ``"help"`` for a known command, or ``None``
    for empty or unrecognised input.
    """
    return _COMMANDS.get(raw.strip().lower())
