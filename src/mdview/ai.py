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


def build_prompt(
    selection: str,
    question: str,
    document: str,
    *,
    svg_out_dir: Path | None = None,
) -> str:
    prompt = (
        "以下は現在開いているMarkdownドキュメントの全文と、その中からユーザーが選択した抜粋です。"
        "このドキュメントの内容を文脈として、簡潔に日本語で質問に答えてください。\n\n"
    )
    if svg_out_dir is not None:
        # The viewer renders SVGs inside the answer popup, so steer Claude to
        # save any diagram into our temp dir (absolute path) instead of writing
        # into the repository, and to keep the prose answer short.
        prompt += (
            "図解する場合は、自己完結した1つの `<svg>` を次の絶対パスのディレクトリ配下にのみ "
            f"`.svg` 拡張子で保存してください（リポジトリ内には書き込まないこと）: {svg_out_dir}\n"
            "保存先パスはユーザーに伝えなくてよく、本文の説明は簡潔にしてください。\n\n"
        )
    return prompt + (
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
    svg_out_dir: Path | None = None,
    timeout: float = 120.0,
) -> str:
    """Run the CLI in print mode with the built prompt and return its stdout.

    Args are passed as a list (no shell), so the selection/question cannot be
    interpreted as shell syntax. When ``svg_out_dir`` is given, the prompt asks
    Claude to save any SVG diagram into that directory so the popup can render
    it. Raises AiQueryError on missing binary, timeout, non-zero exit, or empty
    output.
    """
    prompt = build_prompt(selection, question, document, svg_out_dir=svg_out_dir)
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
