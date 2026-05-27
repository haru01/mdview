"""Modal popup that asks Claude about the current text selection."""

from __future__ import annotations

import hashlib
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, LoadingIndicator, Markdown, Static
from textual_image.widget import Image

from mdview.ai import AiQueryError, ask_claude
from mdview.svg import SvgRenderError, extract_svgs, rasterize_svg


class AskAiScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(
        self, selection: str, document: str, *, claude: str, cwd: Path, tmpdir: Path
    ) -> None:
        super().__init__()
        self._selection = selection
        self._document = document
        self._claude = claude
        self._cwd = cwd
        self._tmpdir = tmpdir
        # Claude saves diagrams here (an absolute path we hand it in the prompt)
        # rather than into the repository; kept in its own subdir so scanning it
        # never picks up the PNG/SVG scratch files rasterization writes alongside.
        self._svg_out_dir = tmpdir / "ai-answer-svg"

    def compose(self) -> ComposeResult:
        with Vertical(id="ask-ai-dialog"):
            yield Static(self._selection_preview(), id="ask-ai-context")
            yield Input(
                value="SVG図解で解説して",
                placeholder="この抜粋について質問… (Enterで送信, Escで閉じる)",
                id="ask-ai-input",
            )
            loading = LoadingIndicator(id="ask-ai-loading")
            loading.display = False
            yield loading
            with VerticalScroll(id="ask-ai-answer"):
                yield Markdown("", id="ask-ai-answer-md")

    def _selection_preview(self) -> str:
        text = " ".join(self._selection.split())
        if len(text) > 200:
            text = text[:200] + "…"
        return f"選択: {text}"

    def on_mount(self) -> None:
        self.query_one("#ask-ai-input", Input).focus()

    def action_dismiss(self) -> None:
        self.dismiss()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if not question:
            return
        self._run_query(question)

    @work(exclusive=True)
    async def _run_query(self, question: str) -> None:
        input_widget = self.query_one("#ask-ai-input", Input)
        loading = self.query_one("#ask-ai-loading", LoadingIndicator)
        answer = self.query_one("#ask-ai-answer-md", Markdown)
        input_widget.disabled = True
        loading.display = True
        await answer.update("")
        await self._clear_images()
        self._reset_svg_out_dir()
        try:
            result = await ask_claude(
                self._selection,
                question,
                self._document,
                claude=self._claude,
                cwd=self._cwd,
                svg_out_dir=self._svg_out_dir,
            )
        except AiQueryError as e:
            await answer.update(f"**エラー:** {e}")
        else:
            # Two sources, both rendered: SVGs Claude saved as files in our temp
            # dir (the common case — `claude -p` writes to disk), and any SVG it
            # inlined into stdout (fallback). Prose is whatever stdout has left.
            inline_svgs, prose = extract_svgs(result)
            svgs = self._read_saved_svgs() + inline_svgs
            rendered = await self._render_svgs(svgs)
            # When a diagram rendered, show the prose beside it; otherwise fall
            # back to the raw answer so the SVG source isn't silently dropped.
            await answer.update(prose if rendered else result)
        finally:
            loading.display = False
            input_widget.disabled = False

    def _reset_svg_out_dir(self) -> None:
        """Start each query with an empty output dir so a re-ask doesn't re-render
        diagrams Claude saved during the previous question."""
        if self._svg_out_dir.exists():
            for stale in self._svg_out_dir.glob("*.svg"):
                stale.unlink()
        self._svg_out_dir.mkdir(parents=True, exist_ok=True)

    def _read_saved_svgs(self) -> list[str]:
        """Return the markup of every SVG Claude wrote into the output dir."""
        if not self._svg_out_dir.exists():
            return []
        return [
            p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(self._svg_out_dir.glob("*.svg"))
        ]

    async def _render_svgs(self, svgs: list[str]) -> int:
        """Rasterize each SVG via a temp file and mount it; return the count shown.

        Diagrams mount above the prose (``before`` the answer Markdown) so the
        figure leads and the text explanation follows beneath it.
        """
        if not svgs:
            return 0
        scroll = self.query_one("#ask-ai-answer", VerticalScroll)
        prose = self.query_one("#ask-ai-answer-md", Markdown)
        rendered = 0
        for svg in svgs:
            widget = self._svg_to_image(svg)
            if widget is not None:
                await scroll.mount(widget, before=prose)
                rendered += 1
        return rendered

    def _svg_to_image(self, svg: str) -> Image | None:
        # Persist the SVG (and its PNG) under the app's temp dir, keyed by a hash
        # of the markup so identical diagrams reuse the same files.
        digest = hashlib.sha1(svg.encode("utf-8")).hexdigest()[:12]
        svg_path = self._tmpdir / f"ask-ai-{digest}.svg"
        png_path = self._tmpdir / f"ask-ai-{digest}.png"
        svg_path.write_text(svg, encoding="utf-8")
        target_width_px = max(400, (self.size.width or 80) * 12)
        try:
            rasterize_svg(svg_path, png_path, width_px=target_width_px)
        except SvgRenderError:
            return None
        return Image(png_path, classes="mdview-image")

    async def _clear_images(self) -> None:
        for image in list(self.query(Image)):
            await image.remove()
