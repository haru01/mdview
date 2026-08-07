"""Pure helpers for the quick-open fuzzy finder (``Ctrl+P`` / ``:e``).

Framework-free so it can be unit-tested without a TUI (the Textual modal that
drives this lives in ``quick_open.py``). Two concerns: enumerate the viewable
files under a directory (recursively, pruning noise dirs), and fuzzily rank a
list against a query — the same subsequence matching fzf/Telescope use, so
``rdme`` finds ``README.md``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from mdview.filetree import is_viewable

T = TypeVar("T")


@dataclass(frozen=True)
class QuickOpenEntry:
    """One pickable row: a display/match `label` and the absolute file `Path`
    to open."""

    label: str
    payload: Path

# Directories never worth walking into for a Markdown viewer: VCS metadata,
# dependency/build trees, tool caches. Any dotted dir is also pruned (hidden).
_IGNORED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
    }
)


def list_viewable_files(root: Path) -> list[Path]:
    """Viewable files under *root*, as root-relative POSIX paths, sorted.

    Recurses with ``os.walk``, pruning ignored/hidden directories in place so
    we never descend into ``.git`` or ``node_modules``. Unreadable subtrees are
    skipped (``os.walk`` swallows the error); the reachable files still return.
    """
    results: list[Path] = []
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _IGNORED_DIRS and not d.startswith(".")
        ]
        base = Path(dirpath)
        for name in filenames:
            path = base / name
            if is_viewable(path):
                results.append(path.relative_to(root))
    results.sort(key=lambda p: p.as_posix())
    return results


def fuzzy_match(query: str, text: str) -> tuple[int, list[int]] | None:
    """Subsequence-match *query* against *text* (case-insensitive).

    Returns ``(score, matched_indices)`` where a lower score is a better match,
    or ``None`` if *query* isn't a subsequence of *text*. An empty query matches
    everything with score 0 and no indices. The score rewards contiguous runs
    and matches at the start of a path segment (after ``/`` or ``.``), and gently
    penalises gaps and long candidates — a deterministic heuristic, no ties on
    randomness.
    """
    if not query:
        return (0, [])

    lowered = text.lower()
    q = query.lower()
    indices: list[int] = []
    score = 0
    pos = 0
    prev_index = -1
    for ch in q:
        found = lowered.find(ch, pos)
        if found == -1:
            return None
        indices.append(found)
        if found == prev_index + 1:
            score -= 5  # contiguous run: strong reward
        else:
            score += found - pos  # gap penalty (chars skipped)
        if found == 0 or text[found - 1] in "/.-_ ":
            score -= 3  # start of a path segment / word boundary
        pos = found + 1
        prev_index = found
    score += len(text) // 10  # mild bias toward shorter candidates
    return (score, indices)


def fuzzy_filter(
    query: str,
    items: list[T],
    key: Callable[[T], str] = str,
) -> list[tuple[T, list[int]]]:
    """Filter and rank *items* against *query*.

    Empty query returns every item in original order with no matched indices.
    Otherwise only matching items survive, ranked by score (best first) with a
    stable tiebreak on original position, each paired with its matched indices
    (offsets into ``key(item)``) for highlighting.
    """
    if not query:
        return [(item, []) for item in items]
    scored: list[tuple[int, int, T, list[int]]] = []
    for order, item in enumerate(items):
        matched = fuzzy_match(query, key(item))
        if matched is not None:
            score, indices = matched
            scored.append((score, order, item, indices))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [(item, indices) for _, _, item, indices in scored]


def build_entries(root: Path, files: list[Path]) -> list[QuickOpenEntry]:
    """The palette rows: each file as an absolute-path payload under *root*."""
    return [QuickOpenEntry(rel.as_posix(), root / rel) for rel in files]
