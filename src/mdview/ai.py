"""Ask Claude Code about selected text, in the open document's context.

Isolated from the TUI so the subprocess logic can be unit tested without textual.
The open document's full text is embedded in the prompt so answers are grounded
in the file being viewed rather than the surrounding repository.
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


def build_prompt(selection: str, question: str, document: str) -> str:
    return (
        "以下は現在開いているMarkdownドキュメントの全文と、その中からユーザーが選択した抜粋です。"
        "このドキュメントの内容を文脈として、簡潔に日本語で質問に答えてください。\n\n"
        f"# ドキュメント全文\n{document}\n\n"
        f"# 選択された抜粋\n{selection}\n\n"
        f"# 質問\n{question}\n"
    )


async def ask_claude(
    selection: str,
    question: str,
    document: str,
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
    prompt = build_prompt(selection, question, document)
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
