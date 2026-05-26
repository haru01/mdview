"""Ask Claude Code about selected text, in the document's repo context.

Isolated from the TUI so the subprocess logic can be unit tested without textual.
Running the CLI with cwd set to the document's repository lets Claude read the
surrounding project files when answering, so questions are grounded in that repo.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path


class AiQueryError(RuntimeError):
    pass


def find_claude() -> str | None:
    """Return the absolute path to a `claude` executable, or None if absent."""
    return shutil.which("claude")


def repo_root_for(path: Path) -> Path:
    """Best-effort repo root for `path`: nearest ancestor holding `.git`, else its dir.

    This is the cwd handed to the CLI so it sees the document's project as context.
    """
    resolved = path.resolve()
    start = resolved if resolved.is_dir() else resolved.parent
    for parent in (start, *start.parents):
        if (parent / ".git").exists():
            return parent
    return start


def build_prompt(selection: str, question: str) -> str:
    return (
        "以下はユーザーが閲覧中のMarkdownから選択した抜粋です。"
        "このリポジトリの文脈を踏まえて、簡潔に日本語で質問に答えてください。\n\n"
        f"# 選択された抜粋\n{selection}\n\n"
        f"# 質問\n{question}\n"
    )


async def ask_claude(
    selection: str,
    question: str,
    *,
    claude: str,
    cwd: Path,
    timeout: float = 120.0,
) -> str:
    """Run the CLI in print mode with the built prompt and return its stdout.

    Args are passed as a list (no shell), so the selection/question cannot be
    interpreted as shell syntax. Raises AiQueryError on missing binary, timeout,
    non-zero exit, or empty output.
    """
    prompt = build_prompt(selection, question)
    try:
        proc = await asyncio.create_subprocess_exec(
            claude,
            "-p",
            prompt,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise AiQueryError(f"claude not found: {claude}") from e

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise AiQueryError(f"claude timed out after {timeout}s") from e

    if proc.returncode != 0:
        msg = (stderr.decode(errors="replace") or stdout.decode(errors="replace")).strip()
        raise AiQueryError(f"claude exited {proc.returncode}: {msg}")

    out = stdout.decode(errors="replace").strip()
    if not out:
        raise AiQueryError("claude produced no output")
    return out
