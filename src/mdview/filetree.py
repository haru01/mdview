"""Pure helpers for the file-tree sidebar: which files are viewable, and which
file to open first when launched on a directory. Framework-free so it can be
unit-tested without a TUI (the Textual wrapper lives in app.py)."""

from __future__ import annotations

from pathlib import Path

# Extensions the viewer can render: Markdown and unified diffs.
VIEWABLE_SUFFIXES = frozenset({".md", ".markdown", ".diff", ".patch"})


def is_viewable(path: Path) -> bool:
    """True if *path* is a file type the viewer renders (case-insensitive)."""
    return path.suffix.lower() in VIEWABLE_SUFFIXES


def initial_file(root: Path) -> Path | None:
    """Pick the file to open when launched on directory *root*: a top-level
    README.md if present, else the first viewable file in sorted order, else
    None (empty directory -> caller shows a placeholder)."""
    try:
        entries = sorted(p for p in root.iterdir() if p.is_file() and is_viewable(p))
    except OSError:
        return None
    for entry in entries:
        if entry.name.lower() == "readme.md":
            return entry
    return entries[0] if entries else None
