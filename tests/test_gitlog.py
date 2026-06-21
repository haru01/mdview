from __future__ import annotations

import subprocess

import pytest

from mdview.diffsource import DiffSourceError
from mdview.gitlog import (
    US,
    Commit,
    capture_log,
    capture_show,
    git_log_command,
    git_show_command,
    parse_log,
)


# --- git_log_command / git_show_command: pure argv building ------------------


def test_git_log_command_default_limit_and_format() -> None:
    argv = git_log_command(50)
    assert argv[:3] == ["git", "log", "--no-color"]
    assert "-50" in argv
    assert any(a.startswith("--pretty=format:") for a in argv)


def test_git_log_command_with_ref() -> None:
    assert "main" in git_log_command(10, "main")


def test_git_log_command_no_ref_omits_it() -> None:
    argv = git_log_command(10)
    # Base command + count + one --pretty token; no stray ref / None / empty.
    assert len(argv) == 5
    assert all(a not in ("None", "") for a in argv)


def test_git_show_command() -> None:
    assert git_show_command("abc123") == ["git", "show", "--no-color", "abc123"]


# --- parse_log: pure parsing -------------------------------------------------


def _log_line(h: str, short: str, author: str, date: str, subject: str) -> str:
    return US.join([h, short, author, date, subject])


def test_parse_log_builds_commits() -> None:
    stdout = "\n".join(
        [
            _log_line("aaaa1111", "aaaa111", "Alice", "2 days ago", "first commit"),
            _log_line("bbbb2222", "bbbb222", "Bob", "5 hours ago", "fix: a bug"),
        ]
    )
    commits = parse_log(stdout)
    assert len(commits) == 2
    assert commits[0] == Commit(
        hash="aaaa1111", short="aaaa111", author="Alice", date="2 days ago", subject="first commit"
    )
    assert commits[1].subject == "fix: a bug"


def test_parse_log_ignores_blank_lines() -> None:
    stdout = _log_line("h", "h", "A", "now", "s") + "\n\n"
    assert len(parse_log(stdout)) == 1


def test_parse_log_subject_may_contain_spaces_and_colons() -> None:
    stdout = _log_line("h", "h", "A", "now", "feat: add x: y, z")
    assert parse_log(stdout)[0].subject == "feat: add x: y, z"


def test_parse_log_empty_is_empty() -> None:
    assert parse_log("") == []


# --- capture_log / capture_show: subprocess wrappers -------------------------


def test_capture_log_missing_binary(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(DiffSourceError, match="git not found on PATH"):
        capture_log(10)


def test_capture_log_nonzero_exit_uses_stderr(monkeypatch) -> None:
    def fake_run(*_a, **_k):
        return subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="fatal: not a git repository"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(DiffSourceError, match="not a git repository"):
        capture_log(10)


def test_capture_log_returns_parsed_commits(monkeypatch) -> None:
    line = _log_line("h1", "h1", "A", "now", "s1")

    def fake_run(*_a, **_k):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=line, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    commits = capture_log(10)
    assert len(commits) == 1
    assert commits[0].short == "h1"


def test_capture_show_returns_stdout(monkeypatch) -> None:
    def fake_run(*_a, **_k):
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout="diff --git a/x b/x\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert capture_show("abc") == "diff --git a/x b/x\n"
