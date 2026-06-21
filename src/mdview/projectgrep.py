"""Project-wide keyword search (pure, framework-free).

The `/` search (`search.py` + the app's `_run_search`) only scans the document
that's open. This module is the cross-file counterpart behind the `Ctrl+G` /
`:grep` finder: enumerate the viewable files under a root (reusing
`quickopen.list_viewable_files`) and scan each line for a query compiled by
`search.compile_query` (so a grep query is the same case-insensitive regex, with
the same literal fallback, as the in-document search).

Kept out of the Textual layer so it's unit-testable without a TUI; the modal that
drives it lives in `project_grep.py`, mirroring the isolation pattern used
elsewhere (`quickopen.py` ↔ `quick_open.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from mdview.quickopen import list_viewable_files
from mdview.search import compile_query

# Cap on total hits so a query matching half the repo can't build an unbounded
# list (and stutter the modal). The caller is told it truncated so it can say so.
_MAX_HITS = 500
# Per-call wall-clock budget: a catastrophic-backtracking pattern is given the
# remaining time as `finditer(timeout=…)`, and a `TimeoutError` ends the scan
# early (treated as truncation) rather than hanging the UI thread.
_BUDGET_S = 2.0


@dataclass(frozen=True)
class GrepHit:
    """One matched line. `path` is absolute (to open), `rel` the root-relative
    POSIX path (to display), `line_no` is 1-based, and `spans` are the matched
    `(start, end)` offsets within `line` (for highlighting)."""

    path: Path
    rel: str
    line_no: int
    line: str
    spans: list[tuple[int, int]]


def grep_files(
    root: Path,
    query: str,
    *,
    files: list[Path] | None = None,
    budget_s: float = _BUDGET_S,
    max_hits: int = _MAX_HITS,
) -> tuple[list[GrepHit], bool]:
    """Search the viewable files under *root* for *query*.

    Returns ``(hits, truncated)``. *truncated* is True when the scan stopped early
    — either it hit *max_hits* or it blew *budget_s* on a pathological pattern —
    so the caller can flag that not everything was searched. An empty query
    yields no hits. *files* (root-relative paths) can be supplied to avoid
    re-walking the tree; otherwise `list_viewable_files(root)` provides them.
    """
    pattern = compile_query(query)
    if pattern is None:
        return ([], False)

    root = Path(root)
    rels = files if files is not None else list_viewable_files(root)
    hits: list[GrepHit] = []
    deadline = monotonic() + budget_s
    try:
        for rel in rels:
            path = root / rel
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue  # unreadable or binary: skip, the rest still searches
            for line_no, line in enumerate(text.splitlines(), start=1):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError
                spans = [
                    m.span()
                    for m in pattern.finditer(line, timeout=remaining)
                    if m.end() > m.start()
                ]
                if spans:
                    hits.append(
                        GrepHit(
                            path=path,
                            rel=rel.as_posix(),
                            line_no=line_no,
                            line=line,
                            spans=spans,
                        )
                    )
                    if len(hits) >= max_hits:
                        return (hits, True)
    except TimeoutError:
        return (hits, True)
    return (hits, False)
