"""Keyword-search matching for the `/` jump feature (pure, framework-free).

The TUI's `/` prompt feeds a raw query here; the app then walks the rendered
block widgets and keeps the ones whose plain text the returned pattern matches
(`pattern.search(...)`). Keeping the regex compilation here — out of the Textual
layer — lets it be unit-tested directly and reused without a running app.

Queries are treated as regular expressions (case-insensitive). This is what
makes the diff search hooks work: a `@ `-prefixed file heading and a `@@ …`
hunk header live in the same searchable text, so `^@ ` selects files only,
`@@` selects hunks only, and `@\\s` (unanchored) selects both. A query that
isn't a valid regex (e.g. a stray `(`) falls back to a literal match so typing
never raises.
"""

from __future__ import annotations

import re

__all__ = ["compile_query"]


def compile_query(query: str) -> re.Pattern[str] | None:
    """Compile *query* into a case-insensitive pattern, or None if it's empty.

    Invalid regexes fall back to a literal (escaped) match so a half-typed
    pattern still searches for the characters as-is instead of erroring.
    """
    if not query:
        return None
    try:
        return re.compile(query, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(query), re.IGNORECASE)
