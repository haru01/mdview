"""Ask Claude Code about selected text, in the open document's context.

Isolated from the TUI so the subprocess logic can be unit tested without textual.
The open document's full text is embedded in the prompt so answers are grounded
in the file being viewed rather than the surrounding repository.
"""

from __future__ import annotations

import asyncio
import re
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
    history: list[tuple[str, str]] | None = None,
) -> str:
    prompt = (
        "以下は現在開いているMarkdownドキュメントの全文と、その中からユーザーが選択した抜粋です。"
        "このドキュメントの内容を文脈として、簡潔に日本語で質問に答えてください。\n\n"
    )
    if svg_out_dir is not None:
        # SVG mode (opt-in): ask for a diagram and have Claude write the `<svg>`
        # *inline* in its reply — which `extract_svgs` lifts out and the popup
        # renders. Inlining (rather than saving to a file) means the diagram
        # arrives without needing the Write tool, so it works in any environment
        # `claude -p` runs in; a headless `claude -p` denies file writes by
        # default, so a save-to-disk diagram silently never appeared. The prose
        # still reads short because the SVG is stripped out of it before display.
        prompt += (
            "回答内容を表すSVG図を作成して解説してください。"
            "自己完結した1つの `<svg>…</svg>` を、応答テキストの中にそのまま（インラインで）出力してください。"
            "ファイルへの保存やツールの使用はせず、応答に直接 `<svg>` を含めること。\n"
            "本文の説明は簡潔にしてください。\n\n"
        )
        if concise_svg:
            # Steer toward a fast, light diagram (e.g. the section-insight feature
            # values speed over a polished illustration).
            prompt += (
                "図は要点が伝わる最小限の要素数でシンプルに描き、凝った装飾やグラデーションは避けて"
                "手早く作成してください。\n\n"
            )
    prompt += f"# ドキュメント全文\n{document}\n\n# 選択された抜粋\n{selection}\n\n"
    if history:
        # A follow-up question: replay the prior turns so the answer stays in
        # thread (the selection above is the fixed context across the whole
        # conversation; this is what changes turn to turn).
        prompt += "# これまでの会話\n"
        for q, a in history:
            prompt += f"## 質問\n{q}\n\n## 回答\n{a}\n\n"
    return prompt + f"# 質問\n{question}\n"


def build_edit_prompt(scope: str, instruction: str) -> str:
    """Prompt asking Claude to rewrite *scope* per *instruction* and return only
    the edited Markdown.

    Only the selected excerpt is sent — no surrounding-document context — and only
    it is to be rewritten. The "Markdown only, no fences, no prose" framing keeps
    the reply directly substitutable into the buffer; any leftover wrapping fence
    is stripped by `strip_code_fence`.
    """
    return (
        "以下のMarkdownの抜粋を、指示に従って書き換えてください。\n\n"
        "出力のルール:\n"
        "- **書き換え後のMarkdownのみ**を出力すること。説明・前置き・後書きは一切付けない。\n"
        "- 全体をコードフェンス(```)で包まないこと（本文中のコードブロックはそのまま残す）。\n"
        "- 抜粋の体裁（見出しレベルなど）は保つこと。\n"
        "- 指示と無関係な箇所は変更しないこと。\n\n"
        f"# 対象の抜粋\n{scope}\n\n"
        f"# 編集の指示\n{instruction}\n"
    )


_OPEN_FENCE = re.compile(r"^(`{3,})([^\n`]*)$")


def strip_code_fence(text: str) -> str:
    """Strip a single code fence wrapping the *entire* reply, if present.

    Claude sometimes wraps an "output only the Markdown" reply in one outer
    fence (``` ``` ``` or ``` ```markdown ```). Only a fence enclosing the whole
    text is removed, and only when its info string is empty or markdown/md — so
    a content block like ```python is preserved. Returns *text* unchanged when
    there is no such wrapper.
    """
    stripped = text.strip()
    lines = stripped.split("\n")
    if len(lines) < 2:
        return text
    opening = _OPEN_FENCE.match(lines[0].strip())
    if opening is None:
        return text
    ticks, info = opening.group(1), opening.group(2).strip().lower()
    if info not in ("", "markdown", "md"):
        return text
    closer = lines[-1].strip()
    if set(closer) != {"`"} or len(closer) < len(ticks):
        return text
    return "\n".join(lines[1:-1])


async def _run_claude(prompt: str, *, claude: str, cwd: Path, timeout: float) -> str:
    """Run `claude -p <prompt>` and return its stripped stdout (shared core).

    Args are passed as a list (no shell), so a selection/instruction cannot be
    interpreted as shell syntax. Raises AiQueryError on missing binary, timeout,
    non-zero exit, or empty output.
    """
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


async def ask_claude(
    selection: str,
    question: str,
    document: str,
    *,
    claude: str,
    cwd: Path,
    svg_out_dir: Path | None = None,
    concise_svg: bool = False,
    history: list[tuple[str, str]] | None = None,
    timeout: float = 120.0,
) -> str:
    """Run the CLI in print mode with the built prompt and return its stdout.

    When ``svg_out_dir`` is given, SVG mode is on: the prompt asks Claude to emit
    an `<svg>` diagram *inline* in its reply (the caller lifts it out with
    `extract_svgs`), which needs no file-write permission. ``svg_out_dir`` is also
    still globbed by callers as a secondary source, so a diagram Claude happens to
    save is picked up too. ``concise_svg`` steers toward a fast, minimal diagram.
    ``history`` (prior (question, answer) turns) makes the answer a follow-up in an
    ongoing conversation rather than a fresh one-shot.
    """
    prompt = build_prompt(
        selection,
        question,
        document,
        svg_out_dir=svg_out_dir,
        concise_svg=concise_svg,
        history=history,
    )
    return await _run_claude(prompt, claude=claude, cwd=cwd, timeout=timeout)


async def edit_markdown(
    scope: str,
    instruction: str,
    *,
    claude: str,
    cwd: Path,
    timeout: float = 120.0,
) -> str:
    """Ask Claude to rewrite *scope* per *instruction*; return the edited Markdown.

    Only *scope* (the selected text) is sent — no document context. Shares the
    subprocess core with `ask_claude` but uses the edit prompt and strips any outer
    code fence so the result is directly substitutable into the buffer. Raises
    AiQueryError on the same failures as `ask_claude`.
    """
    prompt = build_edit_prompt(scope, instruction)
    out = await _run_claude(prompt, claude=claude, cwd=cwd, timeout=timeout)
    return strip_code_fence(out)
