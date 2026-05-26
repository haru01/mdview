from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mdview",
        description="Readable TUI markdown viewer with SVG image rendering.",
    )
    parser.add_argument("file", type=Path, help="markdown file path")
    args = parser.parse_args()

    path: Path = args.file
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
