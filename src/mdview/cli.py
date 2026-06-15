from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mdview.diff import FileDiff


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mdview",
        description="Readable TUI markdown viewer with SVG image rendering.",
    )
    parser.add_argument("file", type=Path, help="markdown file path, or - for stdin")
    args = parser.parse_args()

    path: Path = args.file
    if str(path) == "-":
        _run_stdin()
        return

    if not path.exists():
        print(f"mdview: {path}: no such file", file=sys.stderr)
        sys.exit(1)
    if path.is_dir():
        if not sys.stdout.isatty():
            print(f"mdview: {path}: is a directory", file=sys.stderr)
            sys.exit(1)
        from mdview.app import MdViewerApp
        from mdview.filetree import initial_file

        MdViewerApp(initial_file(path), root_dir=path).run()
        return
    if not path.is_file():
        print(f"mdview: {path}: not a regular file", file=sys.stderr)
        sys.exit(1)

    # `mdview x.diff` / `x.patch`: a unified diff is parsed and rendered in the
    # delta-like style (TUI or non-TTY); anything else is plain Markdown.
    files = _diff_files_for_path(path)

    if not sys.stdout.isatty():
        if files is not None:
            from mdview.render import print_diff

            print_diff(files)
        else:
            from mdview.render import print_markdown

            print_markdown(path)
        return

    from mdview.app import MdViewerApp

    if files is not None:
        from mdview.diff import diff_to_markdown

        MdViewerApp(content=diff_to_markdown(files), base_dir=path.parent, diff_files=files).run()
    else:
        MdViewerApp(path).run()


def _diff_files_for_path(path: Path) -> list[FileDiff] | None:
    """Return the parsed diff model if *path* holds a unified diff, else None."""
    from mdview.diff import looks_like_diff, parse_diff

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return parse_diff(text) if looks_like_diff(text) else None


def _run_stdin() -> None:
    from mdview.diff import looks_like_diff, parse_diff

    # A raw diff (e.g. `gh pr diff | mdview -`) is parsed and rendered delta-like;
    # plain Markdown passes through unchanged.
    text = sys.stdin.read()
    files = parse_diff(text) if looks_like_diff(text) else None

    # When output is going to a real terminal, point stdin at the controlling
    # tty (stdin itself is the now-consumed pipe) so the TUI can read keys.
    # Otherwise just emit rendered text, matching the file-path pipe behavior.
    if sys.stdout.isatty() and _reattach_tty():
        from mdview.app import MdViewerApp

        if files is not None:
            from mdview.diff import diff_to_markdown

            MdViewerApp(content=diff_to_markdown(files), diff_files=files).run()
        else:
            MdViewerApp(content=text).run()
        return

    if files is not None:
        from mdview.render import print_diff

        print_diff(files)
    else:
        from mdview.render import print_markdown_text

        print_markdown_text(text)


def _reattach_tty() -> bool:
    """Redirect fd 0 to /dev/tty. Returns False if no controlling terminal."""
    try:
        tty = open("/dev/tty")
    except OSError:
        return False
    os.dup2(tty.fileno(), sys.stdin.fileno())
    return True
