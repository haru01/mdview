"""Capture a diff from git/gh so the CLI can open it without a manual pipe.

The `--diff`/`--staged`/`--pr` flags (see `cli.py`) let `mdview` run the diff
command itself and feed the captured text into the same detect-and-render path
that `git diff | mdview -` already uses. The argv builder (`diff_command`) is a
pure function so it's unit-testable without spawning a subprocess; `capture_diff`
is the thin subprocess wrapper, mirroring the isolation pattern used elsewhere
(`mermaid.py`, `ai.py`).
"""

from __future__ import annotations

import subprocess


class DiffSourceError(Exception):
    """The diff command was missing on PATH or exited non-zero."""


def diff_command(source: str, ref: str | None) -> list[str]:
    """Build the argv for *source* (`working`/`staged`/`pr`) and optional *ref*.

    `--no-color` guards against a `color.diff = always` git config leaking ANSI
    into the captured text. For `pr`, *ref* is the PR number (None = the PR of
    the current branch, which `gh pr diff` resolves on its own).
    """
    if source == "working":
        return ["git", "diff", "--no-color", *([ref] if ref else [])]
    if source == "staged":
        return ["git", "diff", "--no-color", "--cached"]
    if source == "pr":
        return ["gh", "pr", "diff", *([ref] if ref else [])]
    raise ValueError(f"unknown diff source: {source}")


def capture_diff(source: str, ref: str | None) -> str:
    """Run the diff command and return its stdout.

    Raises `DiffSourceError` when the binary is missing (e.g. no `gh` installed)
    or the command exits non-zero (not a git repo, no PR for the branch, …),
    carrying the command's stderr so the CLI can show why.
    """
    argv = diff_command(source, ref)
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise DiffSourceError(f"{argv[0]} not found on PATH") from e
    if proc.returncode != 0:
        msg = (proc.stderr or "").strip() or f"{argv[0]} exited {proc.returncode}"
        raise DiffSourceError(msg)
    return proc.stdout
