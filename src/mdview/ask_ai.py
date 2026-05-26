"""Modal popup that asks Claude about the current text selection."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, LoadingIndicator, Markdown, Static

from mdview.ai import AiQueryError, ask_claude


class AskAiScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, selection: str, *, claude: str, cwd: Path) -> None:
        super().__init__()
        self._selection = selection
        self._claude = claude
        self._cwd = cwd

    def compose(self) -> ComposeResult:
        with Vertical(id="ask-ai-dialog"):
            yield Static(self._selection_preview(), id="ask-ai-context")
            yield Input(placeholder="この抜粋について質問… (Enterで送信, Escで閉じる)", id="ask-ai-input")
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
        try:
            result = await ask_claude(
                self._selection,
                question,
                claude=self._claude,
                cwd=self._cwd,
            )
        except AiQueryError as e:
            await answer.update(f"**エラー:** {e}")
        else:
            await answer.update(result)
        finally:
            loading.display = False
            input_widget.disabled = False
