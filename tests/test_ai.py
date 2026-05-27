from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path

import pytest

from mdview.ai import AiQueryError, ask_claude, build_prompt


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


def test_build_prompt_includes_document_selection_and_question() -> None:
    prompt = build_prompt("選択テキスト", "これは何?", "# ドキュメント本文")
    assert "ドキュメント本文" in prompt
    assert "選択テキスト" in prompt
    assert "これは何?" in prompt


def test_build_prompt_without_svg_dir_has_no_save_instruction() -> None:
    prompt = build_prompt("s", "q", "doc")
    assert ".svg" not in prompt


def test_build_prompt_with_svg_dir_instructs_saving_to_that_absolute_path(
    tmp_path: Path,
) -> None:
    svg_dir = tmp_path / "out"
    prompt = build_prompt("s", "q", "doc", svg_out_dir=svg_dir)
    # The absolute output directory must appear so Claude saves SVGs there...
    assert str(svg_dir) in prompt
    # ...and the instruction must mention the .svg extension.
    assert ".svg" in prompt


def test_ask_claude_returns_stdout_runs_in_cwd_and_embeds_document(tmp_path: Path) -> None:
    workdir = tmp_path / "docs"
    workdir.mkdir()
    claude = _fake_claude(tmp_path, stdout="42 です")

    result = asyncio.run(
        ask_claude("抜粋", "答えは?", "# 開いている本文", claude=str(claude), cwd=workdir)
    )
    assert result == "42 です"
    # The CLI must have run with cwd set to the document's directory.
    assert (tmp_path / "cwd.log").read_text().strip() == str(workdir)
    # The prompt is passed after `-p` as a single positional arg containing the
    # open document's text, the selection, and the question.
    argv = (tmp_path / "argv.log").read_bytes().split(b"\0")
    assert argv[0] == b"-p"
    assert "開いている本文".encode() in argv[1]
    assert "抜粋".encode() in argv[1]


def test_ask_claude_raises_on_nonzero_exit(tmp_path: Path) -> None:
    claude = _fake_claude(tmp_path, exit_code=2, stdout="", stderr="boom")
    with pytest.raises(AiQueryError, match="boom"):
        asyncio.run(ask_claude("s", "q", "doc", claude=str(claude), cwd=tmp_path))


def test_ask_claude_raises_on_empty_output(tmp_path: Path) -> None:
    claude = _fake_claude(tmp_path, stdout="")
    with pytest.raises(AiQueryError, match="no output"):
        asyncio.run(ask_claude("s", "q", "doc", claude=str(claude), cwd=tmp_path))


def test_ask_claude_raises_on_missing_binary(tmp_path: Path) -> None:
    with pytest.raises(AiQueryError, match="not found"):
        asyncio.run(
            ask_claude("s", "q", "doc", claude=str(tmp_path / "nope"), cwd=tmp_path)
        )
