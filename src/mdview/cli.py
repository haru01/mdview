from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Unified diffs are not a document type the viewer renders. Rejecting by *name*
# only: content sniffing went with the diff viewer, so a diff under another name
# (or piped in) still renders as Markdown. This catches the common mistake
# cheaply — it is not meant to be exhaustive.
_DIFF_SUFFIXES = frozenset({".diff", ".patch"})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdview",
        description="Readable TUI markdown viewer with SVG image rendering.",
    )
    parser.add_argument("file", type=Path, help="markdown file path, or - for stdin")
    return parser


def main() -> None:
    args = _build_parser().parse_args()

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
    if path.suffix.lower() in _DIFF_SUFFIXES:
        print(f"mdview: {path}: diff files are not supported", file=sys.stderr)
        sys.exit(1)

    if not sys.stdout.isatty():
        from mdview.render import print_markdown

        print_markdown(path)
        return

    from mdview.app import MdViewerApp

    MdViewerApp(path).run()


def _run_stdin() -> None:
    """`mdview -`: view piped text (TUI) or render it (non-TTY stdout).

    stdin is the now-consumed pipe, so the TUI path needs the controlling tty
    re-pointed onto fd 0 before Textual can read keys.
    """
    text = sys.stdin.read()

    if sys.stdout.isatty() and _reattach_tty():
        from mdview.app import MdViewerApp

        MdViewerApp(content=text).run()
        return

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
