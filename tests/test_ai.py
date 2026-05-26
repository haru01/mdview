from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path

import pytest

from mdview.ai import AiQueryError, ask_claude, build_prompt, repo_root_for


def _fake_claude(tmp_path: Path, *, exit_code: int = 0, stdout: str = "ok", stderr: str = "") -> Path:
    """Create a fake `claude` shell script that echoes a fixed reply and logs argv.

    The real `claude -p <prompt>` reads the prompt as a positional arg and writes
    its answer to stdout; this stub mirrors that contract.
    """
    script = tmp_path / "claude"
    argv_log = tmp_path / "argv.log"
    cwd_log = tmp_path / "cwd.log"
    body = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        printf '%s\\0' "$@" > "{argv_log}"
        pwd > "{cwd_log}"
        printf '%s' {stdout!r}
        printf '%s' {stderr!r} >&2
        exit {exit_code}
        """
    )
    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    return script


def test_build_prompt_includes_selection_and_question() -> None:
    prompt = build_prompt("選択テキスト", "これは何?")
    assert "選択テキスト" in prompt
    assert "これは何?" in prompt


def test_repo_root_finds_git_ancestor(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "docs" / "guide"
    nested.mkdir(parents=True)
    doc = nested / "page.md"
    doc.write_text("# x", encoding="utf-8")
    assert repo_root_for(doc) == tmp_path.resolve()


def test_repo_root_falls_back_to_file_dir(tmp_path: Path) -> None:
    doc = tmp_path / "page.md"
    doc.write_text("# x", encoding="utf-8")
    assert repo_root_for(doc) == tmp_path.resolve()


def test_ask_claude_returns_stdout_and_runs_in_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    claude = _fake_claude(tmp_path, stdout="42 です")

    result = asyncio.run(
        ask_claude("抜粋", "答えは?", claude=str(claude), cwd=repo)
    )
    assert result == "42 です"
    # The CLI must have run with cwd set to the document's repo.
    assert (tmp_path / "cwd.log").read_text().strip() == str(repo)
    # The prompt is passed after `-p` as a single positional arg.
    argv = (tmp_path / "argv.log").read_bytes().split(b"\0")
    assert argv[0] == b"-p"
    assert "抜粋".encode() in argv[1]


def test_ask_claude_raises_on_nonzero_exit(tmp_path: Path) -> None:
    claude = _fake_claude(tmp_path, exit_code=2, stdout="", stderr="boom")
    with pytest.raises(AiQueryError, match="boom"):
        asyncio.run(ask_claude("s", "q", claude=str(claude), cwd=tmp_path))


def test_ask_claude_raises_on_empty_output(tmp_path: Path) -> None:
    claude = _fake_claude(tmp_path, stdout="")
    with pytest.raises(AiQueryError, match="no output"):
        asyncio.run(ask_claude("s", "q", claude=str(claude), cwd=tmp_path))


def test_ask_claude_raises_on_missing_binary(tmp_path: Path) -> None:
    with pytest.raises(AiQueryError, match="not found"):
        asyncio.run(
            ask_claude("s", "q", claude=str(tmp_path / "nope"), cwd=tmp_path)
        )
