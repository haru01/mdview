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
    concise_svg: bool = False,
) -> str:
    prompt = (
        "以下は現在開いているMarkdownドキュメントの全文と、その中からユーザーが選択した抜粋です。"
        "このドキュメントの内容を文脈として、簡潔に日本語で質問に答えてください。\n\n"
    )
    if svg_out_dir is not None:
        # SVG mode (opt-in): ask for a diagram and steer Claude to save it into
        # our temp dir (absolute path) — which the popup renders — instead of
        # writing into the repository, keeping the prose answer short.
        prompt += (
            "回答内容を表すSVG図を作成して解説してください。自己完結した1つの `<svg>` を、"
            f"次の絶対パスのディレクトリ配下にのみ `.svg` 拡張子で保存してください（リポジトリ内には書き込まないこと）: {svg_out_dir}\n"
            "保存先パスはユーザーに伝える必要はなく、本文の説明は簡潔にしてください。\n\n"
        )
        if concise_svg:
            # Steer toward a fast, light diagram (e.g. the section-insight feature
            # values speed over a polished illustration).
            prompt += (
                "図は要点が伝わる最小限の要素数でシンプルに描き、凝った装飾やグラデーションは避けて"
                "手早く作成してください。\n\n"
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
    concise_svg: bool = False,
    timeout: float = 120.0,
) -> str:
    """Run the CLI in print mode with the built prompt and return its stdout.

    Args are passed as a list (no shell), so the selection/question cannot be
    interpreted as shell syntax. When ``svg_out_dir`` is given, the prompt asks
    Claude to save any SVG diagram into that directory so the popup can render
    it; ``concise_svg`` additionally steers toward a fast, minimal diagram.
    Raises AiQueryError on missing binary, timeout, non-zero exit, or empty
    output.
    """
    prompt = build_prompt(
        selection, question, document, svg_out_dir=svg_out_dir, concise_svg=concise_svg
    )
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
