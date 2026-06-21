from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mdview.diff import FileDiff


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdview",
        description="Readable TUI markdown viewer with SVG image rendering.",
    )
    parser.add_argument(
        "file", nargs="?", type=Path, help="markdown file path, or - for stdin"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--diff",
        nargs="?",
        const="",
        metavar="REF",
        help="show `git diff [REF]` (no REF = working tree)",
    )
    group.add_argument(
        "--staged", action="store_true", help="show `git diff --cached`"
    )
    group.add_argument(
        "--pr",
        nargs="?",
        const="",
        metavar="N",
        help="show a PR diff via `gh pr diff [N]` (no N = current branch)",
    )
    group.add_argument(
        "--log",
        action="store_true",
        help="browse recent commits (`git log`); pick one to view its diff",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # `--log`: browse commits (TUI) or print the recent log (non-TTY).
    if args.log:
        if args.file is not None:
            parser.error("--log cannot be combined with a file argument")
        _run_log()
        return

    # `--diff`/`--staged`/`--pr`: run the diff command ourselves and view its
    # output, so no manual `git diff | mdview -` pipe is needed.
    source = _resolve_source(args)
    if source is not None:
        if args.file is not None:
            parser.error(
                "--diff/--staged/--pr cannot be combined with a file argument"
            )
        _run_source(*source)
        return
    if args.file is None:
        parser.error("a file, - (stdin), or one of --diff/--staged/--pr is required")

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


def _resolve_source(args: argparse.Namespace) -> tuple[str, str | None] | None:
    """Map the `--diff`/`--staged`/`--pr` flags to a (source, ref) pair, or None."""
    if args.diff is not None:
        return ("working", args.diff or None)  # "" → None (working tree), else a ref
    if args.staged:
        return ("staged", None)
    if args.pr is not None:
        return ("pr", args.pr or None)  # "" → None (current branch), else a PR number
    return None


def _run_source(source: str, ref: str | None) -> None:
    from mdview.diffsource import DiffSourceError, capture_diff

    try:
        text = capture_diff(source, ref)
    except DiffSourceError as e:
        print(f"mdview: {e}", file=sys.stderr)
        sys.exit(1)
    if not text.strip():
        print("mdview: no changes to show", file=sys.stderr)
        return
    # Launched from a terminal, so stdin is already the tty — no reattach needed.
    _view_captured(text, reattach=False)


def _run_log() -> None:
    """`mdview --log`: open the commit browser (TUI) or print the log (non-TTY)."""
    if not sys.stdout.isatty():
        from mdview.gitlog import DEFAULT_LOG_LIMIT, DiffSourceError, capture_log

        try:
            commits = capture_log(DEFAULT_LOG_LIMIT)
        except DiffSourceError as e:
            print(f"mdview: {e}", file=sys.stderr)
            sys.exit(1)
        if not commits:
            print("mdview: no commits", file=sys.stderr)
            return
        for c in commits:
            print(f"{c.short}  {c.subject}  ({c.author}, {c.date})")
        return

    from mdview.app import MdViewerApp

    MdViewerApp(None, root_dir=Path.cwd(), open_log=True).run()


def _run_stdin() -> None:
    # A raw diff (e.g. `gh pr diff | mdview -`) is parsed and rendered delta-like;
    # plain Markdown passes through unchanged. stdin is the now-consumed pipe, so
    # the TUI path needs the controlling tty re-pointed onto fd 0.
    _view_captured(sys.stdin.read(), reattach=True)


def _view_captured(text: str, *, reattach: bool) -> None:
    """Detect a diff in *text* and view it (TUI) or render it (non-TTY stdout).

    When *reattach* is True (stdin path) and a terminal is present, fd 0 is
    re-pointed at /dev/tty so the TUI can read keys; the flag path passes False
    because it runs from a terminal where stdin is already the tty.
    """
    from mdview.diff import looks_like_diff, parse_diff

    files = parse_diff(text) if looks_like_diff(text) else None

    if sys.stdout.isatty() and (not reattach or _reattach_tty()):
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
