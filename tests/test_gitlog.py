from __future__ import annotations

import subprocess

import pytest

from mdview.diffsource import DiffSourceError
from mdview.gitlog import (
    US,
    Commit,
    capture_log,
    capture_show,
    commit_markdown_header,
    git_log_command,
    git_show_command,
    parse_log,
    split_show,
)


# --- split_show: separate `git show` metadata from the unified diff ----------

_GIT_SHOW = """\
commit aaaa1111bbbb2222cccc3333
Author: Alice <alice@example.com>
Date:   Mon Jun 16 10:00:00 2026 +0900

    feat: add the thing

    A longer body line explaining the thing.

diff --git a/foo.py b/foo.py
index 111..222 100644
--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,2 @@
-old
+new
"""


def test_split_show_separates_message_and_diff() -> None:
    message, diff = split_show(_GIT_SHOW)
    # The diff portion starts at `diff --git` and is itself diff-detectable.
    assert diff.startswith("diff --git a/foo.py b/foo.py")
    from mdview.diff import looks_like_diff

    assert looks_like_diff(diff)
    # The message is de-indented (no leading 4 spaces) and drops the
    # commit/Author/Date headers.
    assert "feat: add the thing" in message
    assert "A longer body line" in message
    assert "Author:" not in message
    assert "commit aaaa1111" not in message
    assert not message.startswith("    ")


def test_split_show_plain_diff_has_no_message() -> None:
    plain = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
    message, diff = split_show(plain)
    assert message == ""
    assert diff == plain


def test_split_show_no_diff_returns_message_only() -> None:
    # An empty/merge commit with no file changes.
    text = "commit deadbeef\nAuthor: A\nDate:   now\n\n    just a message\n"
    message, diff = split_show(text)
    assert diff == ""
    assert "just a message" in message


def test_commit_markdown_header_includes_subject_meta_and_body() -> None:
    commit = Commit(
        hash="aaaa1111", short="aaaa111", author="Alice", date="2 days ago", subject="feat: add the thing"
    )
    md = commit_markdown_header(commit, "feat: add the thing\n\nA longer body line.")
    assert "# feat: add the thing" in md
    assert "aaaa111" in md
    assert "Alice" in md
    assert "2 days ago" in md
    assert "A longer body line." in md
    # The subject isn't duplicated as body text below the metadata line.
    assert md.count("A longer body line.") == 1


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
