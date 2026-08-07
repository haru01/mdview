"""Modal popup that asks Claude about the current text selection."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer, Vertical, VerticalScroll
from textual.widgets import Checkbox, Input, LoadingIndicator, Markdown, Static

from mdview.ai import AiQueryError, ask_claude
from mdview.scroll_modal import ScrollableModalScreen
from mdview.svg import extract_svgs
from mdview.svg_widgets import render_svgs_into


class SelectionViewScreen(ScrollableModalScreen):
    """Nested modal showing the full selected text.

    The Ask AI context line only previews the selection (whitespace-collapsed,
    truncated); clicking it opens this to read the whole thing. The text is
    re-rendered with a Markdown widget so it shares the *main view's* colours and
    line spacing (theme.css styles `Markdown`/`MarkdownBlock` by type, so a bare
    `Markdown` here inherits them). Scrollable via the inherited movement keys.
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
        # The conversation so far, as (question, answer) turns. The selection is
        # the fixed context across the whole thread; this is what each follow-up
        # adds. Replayed to `ask_claude(history=…)` so answers stay in thread.
        self._history: list[tuple[str, str]] = []
        # Monotonic turn counter, only for unique answer-widget ids.
        self._turn = 0

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
            yield Checkbox("SVGで図解する", value=True, id="ask-ai-svg-toggle")
            loading = LoadingIndicator(id="ask-ai-loading")
            loading.display = False
            yield loading
            # Each turn appends a question header + its own answer Markdown here,
            # so the popup reads as a conversation rather than a single reply.
            yield VerticalScroll(id="ask-ai-answer")

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

    async def _mount_turn(self, question: str) -> Markdown:
        """Append this turn's question header + a fresh answer Markdown, returning
        the latter so the reply (and any diagrams) land in it."""
        scroll = self.query_one("#ask-ai-answer", VerticalScroll)
        self._turn += 1
        header = Static(f"❯ {question}", classes="ask-ai-question")
        answer = Markdown("", id=f"ask-ai-answer-{self._turn}")
        await scroll.mount(header)
        await scroll.mount(answer)
        # Remembered so the finally block can bring this turn's start into view
        # (the question, then its diagram, then the prose) rather than the very
        # bottom — which would scroll a leading diagram out of sight.
        self._last_turn_header = header
        return answer

    @work(exclusive=True)
    async def _run_query(self, question: str) -> None:
        input_widget = self.query_one("#ask-ai-input", Input)
        loading = self.query_one("#ask-ai-loading", LoadingIndicator)
        # SVG diagramming is opt-in via the checkbox; otherwise the answer is
        # plain text and we neither ask Claude for an SVG nor render one.
        svg_mode = self.query_one("#ask-ai-svg-toggle", Checkbox).value
        input_widget.disabled = True
        loading.display = True
        answer = await self._mount_turn(question)
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
                history=self._history,
            )
        except AiQueryError as e:
            await answer.update(f"**エラー:** {e}")
        else:
            if not svg_mode:
                await answer.update(result)
                self._history.append((question, result))
            else:
                # Two sources, both rendered: SVGs Claude saved as files in our
                # temp dir (the common case — `claude -p` writes to disk), and
                # any SVG inlined into stdout (fallback). Prose is what's left.
                inline_svgs, prose = extract_svgs(result)
                svgs = self._read_saved_svgs() + inline_svgs
                rendered = await self._render_svgs(svgs, before=answer)
                # With a diagram shown, display the prose beside it; otherwise
                # fall back to the raw answer so the SVG source isn't dropped.
                shown = prose if rendered else result
                await answer.update(shown)
                self._history.append((question, shown))
        finally:
            loading.display = False
            input_widget.disabled = False
            # Keep the line open for a follow-up: clear it, refocus, and bring
            # the latest turn's start into view (header → diagram → prose).
            input_widget.value = ""
            input_widget.focus()
            scroll = self.query_one("#ask-ai-answer", VerticalScroll)
            scroll.scroll_to_widget(self._last_turn_header, top=True, animate=False)

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

    async def _render_svgs(self, svgs: list[str], *, before: Markdown) -> int:
        """Rasterize each SVG and mount it above *before* (this turn's prose, so
        the figure leads and the explanation follows beneath it); return the
        count shown."""
        if not svgs:
            return 0
        scroll = self.query_one("#ask-ai-answer", VerticalScroll)
        return await render_svgs_into(
            scroll,
            svgs,
            self._tmpdir,
            width_hint=max(400, (self.size.width or 80) * 12),
            before=before,
            prefix="ask-ai",
        )
