"""Keyword-search matching for the `/` jump feature (pure, framework-free).

The TUI's `/` prompt feeds a raw query here; the app then walks the rendered
block widgets and keeps the ones whose plain text the returned pattern matches.
Keeping the compilation here — out of the Textual layer — lets it be unit-tested
directly and reused without a running app.

Queries are treated as regular expressions (case-insensitive), so anchors and
character classes work as typed. A query that isn't a valid regex (e.g. a stray
`(`) falls back to a literal match so typing never raises.

We compile with the `regex` module (a superset of stdlib `re`) so the caller can
pass a per-call `timeout=` to `finditer`: a catastrophic-backtracking pattern
typed into the box would otherwise hang the UI thread (stdlib `re` has no
timeout and the backtracking runs in C, ignoring signals).
"""

from __future__ import annotations

import regex

__all__ = ["compile_query"]


def compile_query(query: str) -> regex.Pattern[str] | None:
    """Compile *query* into a case-insensitive pattern, or None if it's empty.

    Invalid regexes fall back to a literal (escaped) match so a half-typed
    pattern still searches for the characters as-is instead of erroring.
    """
    if not query:
        return None
    try:
        return regex.compile(query, regex.IGNORECASE)
    except regex.error:
        return regex.compile(regex.escape(query), regex.IGNORECASE)
