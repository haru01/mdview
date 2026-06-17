from __future__ import annotations

import subprocess

import pytest

from mdview.diffsource import DiffSourceError, capture_diff, diff_command


# --- diff_command: pure argv building ---------------------------------------


def test_diff_command_working_no_ref() -> None:
    assert diff_command("working", None) == ["git", "diff", "--no-color"]


def test_diff_command_working_with_ref() -> None:
    assert diff_command("working", "main") == ["git", "diff", "--no-color", "main"]


def test_diff_command_staged() -> None:
    assert "--cached" in diff_command("staged", None)


def test_diff_command_pr_no_number() -> None:
    assert diff_command("pr", None) == ["gh", "pr", "diff"]


def test_diff_command_pr_with_number() -> None:
    assert diff_command("pr", "123") == ["gh", "pr", "diff", "123"]


def test_diff_command_unknown_source() -> None:
    with pytest.raises(ValueError):
        diff_command("bogus", None)


# --- capture_diff: subprocess wrapper ---------------------------------------


def test_capture_diff_missing_binary(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(DiffSourceError, match="git not found on PATH"):
        capture_diff("working", None)


def test_capture_diff_nonzero_exit_uses_stderr(monkeypatch) -> None:
    def fake_run(*_a, **_k):
        return subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="fatal: not a git repository"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(DiffSourceError, match="not a git repository"):
        capture_diff("working", None)


def test_capture_diff_returns_stdout(monkeypatch) -> None:
    def fake_run(*_a, **_k):
        return subprocess.CompletedProcess(
            args=[], returncode=0, stdout="diff --git a/x b/x\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert capture_diff("working", None) == "diff --git a/x b/x\n"
