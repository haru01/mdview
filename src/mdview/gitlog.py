"""Capture and parse `git log` so the commit browser can list commits.

The `--diff`/`--staged`/`--pr` flags (`diffsource.py`) show a single diff; this
module backs the `--log` flag / `:log` command, which lists commits and opens the
diff of whichever one you pick. The argv builders (`git_log_command`,
`git_show_command`) and the parser (`parse_log`) are pure so they're unit-testable
without spawning git; `capture_log`/`capture_show` are the thin subprocess wrappers
(mirroring `diffsource.py`, whose `DiffSourceError` is reused so the app's diff
error handling covers this too).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from mdview.diffsource import DiffSourceError

# Field separator in the `git log` pretty-format. ASCII Unit Separator (0x1f) —
# can't appear in hashes/names/dates and is vanishingly unlikely in a subject, so
# splitting on it is safe where splitting on whitespace/`|` would not be.
US = "\x1f"

_PRETTY = f"--pretty=format:%H{US}%h{US}%an{US}%ar{US}%s"

# Default number of commits the browser / `--log` lists (most-recent first).
DEFAULT_LOG_LIMIT = 100


@dataclass(frozen=True)
class Commit:
    """One log entry. `hash` is the full SHA (fed to `git show`), `short` the
    abbreviated SHA, `author`/`date` are display strings (`%an`/`%ar`), and
    `subject` is the first commit-message line."""

    hash: str
    short: str
    author: str
    date: str
    subject: str


def git_log_command(limit: int, ref: str | None = None) -> list[str]:
    """Build the argv for ``git log`` of the last *limit* commits on *ref* (None =
    the current branch / HEAD). Fields are emitted US-separated for `parse_log`."""
    return ["git", "log", "--no-color", f"-{limit}", _PRETTY, *([ref] if ref else [])]


def git_show_command(commit_hash: str) -> list[str]:
    """Build the argv for ``git show`` of one commit (its diff + metadata)."""
    return ["git", "show", "--no-color", commit_hash]


def parse_log(stdout: str) -> list[Commit]:
    """Parse US-separated `git log` output into a list of `Commit`s.

    Blank lines are skipped; a line with fewer than the expected fields is
    ignored (defensive against a malformed entry). The subject keeps any spaces
    and colons it contains because the split is bounded to the field count.
    """
    commits: list[Commit] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(US, 4)  # subject (last) may itself contain US-safe text
        if len(parts) < 5:
            continue
        h, short, author, date, subject = parts
        commits.append(
            Commit(hash=h, short=short, author=author, date=date, subject=subject)
        )
    return commits


def capture_log(limit: int, ref: str | None = None) -> list[Commit]:
    """Run `git log` and return the parsed commits.

    Raises `DiffSourceError` when git is missing or exits non-zero (not a repo,
    bad ref, …), carrying the command's stderr — same contract as `capture_diff`.
    """
    return parse_log(_run(git_log_command(limit, ref)))


def capture_show(commit_hash: str) -> str:
    """Run `git show` for *commit_hash* and return its diff text (raises as above)."""
    return _run(git_show_command(commit_hash))


def _run(argv: list[str]) -> str:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise DiffSourceError(f"{argv[0]} not found on PATH") from e
    if proc.returncode != 0:
        msg = (proc.stderr or "").strip() or f"{argv[0]} exited {proc.returncode}"
        raise DiffSourceError(msg)
    return proc.stdout
