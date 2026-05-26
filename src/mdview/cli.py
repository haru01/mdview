from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


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
    if not path.is_file():
        print(f"mdview: {path}: not a regular file", file=sys.stderr)
        sys.exit(1)

    if not sys.stdout.isatty():
        from mdview.render import print_markdown

        print_markdown(path)
        return

    from mdview.app import MdViewerApp

    MdViewerApp(path).run()


def _run_stdin() -> None:
    content = sys.stdin.read()
    # When output is going to a real terminal, point stdin at the controlling
    # tty (stdin itself is the now-consumed pipe) so the TUI can read keys.
    # Otherwise just emit rendered text, matching the file-path pipe behavior.
    if sys.stdout.isatty() and _reattach_tty():
        from mdview.app import MdViewerApp

        MdViewerApp(content=content).run()
        return

    from mdview.render import print_markdown_text

    print_markdown_text(content)


def _reattach_tty() -> bool:
    """Redirect fd 0 to /dev/tty. Returns False if no controlling terminal."""
    try:
        tty = open("/dev/tty")
    except OSError:
        return False
    os.dup2(tty.fileno(), sys.stdin.fileno())
    return True
