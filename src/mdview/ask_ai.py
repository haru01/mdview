"""Modal popup that asks Claude about the current text selection."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer, Vertical, VerticalScroll
from textual.widgets import Checkbox, Input, LoadingIndicator, Markdown, Static

from mdview.ai import AiQueryError, ask_claude
from mdview.diffview import is_diff_text, render_selection
from mdview.image_zoom import ZoomableImage
from mdview.scroll_modal import ScrollableModalScreen
from mdview.svg import extract_svgs
from mdview.svg_widgets import render_svgs_into


class SelectionViewScreen(ScrollableModalScreen):
    """Nested modal showing the full selected text.

    The Ask AI context line only previews the selection (whitespace-collapsed,
    truncated); clicking it opens this to read the whole thing. A diff selection
    gets the delta look (`render_selection`); everything else is re-rendered with
    a Markdown widget so it shares the *main view's* colours and line spacing
    (theme.css styles `Markdown`/`MarkdownBlock` by type, so a bare `Markdown`
    here inherits them). Scrollable via the inherited movement keys.
    """

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
    ]

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        with Container(id="selection-view-dialog") as dialog:
            dialog.border_title = "選択テキスト"
            with VerticalScroll(id="selection-view-body"):
                if is_diff_text(self._text):
                    yield Static(render_selection(self._text))
                else:
                    yield Markdown(self._text)

    def scroll_region(self) -> ScrollableContainer:
        return self.query_one("#selection-view-body", VerticalScroll)

    def action_dismiss(self) -> None:
        self.dismiss()


class _SelectionContext(Static):
    """The Ask AI context line. Shows the truncated preview but holds the full
    selection; clicking it opens `SelectionViewScreen` (cf. ZoomableImage)."""

    def __init__(self, preview: str, *, full: str, **kwargs) -> None:
        super().__init__(preview, **kwargs)
        self._full = full

    def on_click(self) -> None:
        self.app.push_screen(SelectionViewScreen(self._full))


class AskAiScreen(ScrollableModalScreen):
    # Movement keys scroll the (often long) answer; while the question Input is
    # focused they type instead, so scroll the answer with arrows/PageUp/PageDown
    # there (see ScrollableModalScreen).
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
            yield _SelectionContext(
                self._selection_preview(), full=self._selection, id="ask-ai-context"
            )
            yield Input(
                value="わかりやすく解説して",
                placeholder="この抜粋について質問… (Enterで送信, Escで閉じる)",
                id="ask-ai-input",
            )
            yield Checkbox("SVGで図解する", value=False, id="ask-ai-svg-toggle")
            loading = LoadingIndicator(id="ask-ai-loading")
            loading.display = False
            yield loading
            with VerticalScroll(id="ask-ai-answer"):
                yield Markdown("", id="ask-ai-answer-md")

    def _selection_preview(self) -> str:
        text = " ".join(self._selection.split())
        if len(text) > 200:
            text = text[:200] + "…"
        return f"選択: {text}  （クリックで全文）"

    def on_mount(self) -> None:
        self.query_one("#ask-ai-input", Input).focus()

    def scroll_region(self) -> ScrollableContainer:
        return self.query_one("#ask-ai-answer", VerticalScroll)

    def action_dismiss(self) -> None:
        self.dismiss()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        # Hand focus back to the input so Enter sends the question rather than
        # toggling the checkbox again.
        self.query_one("#ask-ai-input", Input).focus()

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
        # SVG diagramming is opt-in via the checkbox; otherwise the answer is
        # plain text and we neither ask Claude for an SVG nor render one.
        svg_mode = self.query_one("#ask-ai-svg-toggle", Checkbox).value
        input_widget.disabled = True
        loading.display = True
        await answer.update("")
        await self._clear_images()
        svg_out_dir = None
        if svg_mode:
            self._reset_svg_out_dir()
            svg_out_dir = self._svg_out_dir
        try:
            result = await ask_claude(
                self._selection,
                question,
                self._document,
                claude=self._claude,
                cwd=self._cwd,
                svg_out_dir=svg_out_dir,
            )
        except AiQueryError as e:
            await answer.update(f"**エラー:** {e}")
        else:
            if not svg_mode:
                await answer.update(result)
            else:
                # Two sources, both rendered: SVGs Claude saved as files in our
                # temp dir (the common case — `claude -p` writes to disk), and
                # any SVG inlined into stdout (fallback). Prose is what's left.
                inline_svgs, prose = extract_svgs(result)
                svgs = self._read_saved_svgs() + inline_svgs
                rendered = await self._render_svgs(svgs)
                # With a diagram shown, display the prose beside it; otherwise
                # fall back to the raw answer so the SVG source isn't dropped.
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
        """Rasterize each SVG and mount it above the prose (so the figure leads
        and the explanation follows beneath it); return the count shown."""
        if not svgs:
            return 0
        scroll = self.query_one("#ask-ai-answer", VerticalScroll)
        prose = self.query_one("#ask-ai-answer-md", Markdown)
        return await render_svgs_into(
            scroll,
            svgs,
            self._tmpdir,
            width_hint=max(400, (self.size.width or 80) * 12),
            before=prose,
            prefix="ask-ai",
        )

    async def _clear_images(self) -> None:
        for image in list(self.query(ZoomableImage)):
            await image.remove()
