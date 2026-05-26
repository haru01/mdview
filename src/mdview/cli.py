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

    # `mdview x.diff` / `x.patch`: rewrite a diff file the same way piped diffs
    # are, then render from the transformed Markdown via the content path.
    diff_md = _diff_markdown_for_file(path)

    if not sys.stdout.isatty():
        if diff_md is not None:
            from mdview.render import print_markdown_text

            print_markdown_text(diff_md)
        else:
            from mdview.render import print_markdown

            print_markdown(path)
        return

    from mdview.app import MdViewerApp

    if diff_md is not None:
        MdViewerApp(content=diff_md, base_dir=path.parent).run()
    else:
        MdViewerApp(path).run()


def _diff_markdown_for_file(path: Path) -> str | None:
    """Return structured Markdown if *path* holds a unified diff, else None."""
    from mdview.diff import diff_to_markdown, looks_like_diff

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return diff_to_markdown(text) if looks_like_diff(text) else None


def _run_stdin() -> None:
    from mdview.diff import maybe_diff_to_markdown

    # A raw diff (e.g. `gh pr diff | mdview -`) is rewritten into structured,
    # navigable Markdown before rendering; plain Markdown passes through.
    content = maybe_diff_to_markdown(sys.stdin.read())
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
