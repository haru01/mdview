"""Modal that collects an edit instruction and runs `claude -p` to rewrite a scope.

The entry point of the AI edit loop. The reader sees a preview of the scope being
edited (clickable to read it in full — reusing Ask AI's `_SelectionContext`) and
types a natural-language instruction. On submit, `ai.edit_markdown` runs in a
worker; on success the screen dismisses with the edited Markdown so the app can
show a diff preview and own the buffer/undo state. An error surfaces as a notice
and leaves the box open to retry. Cancelling (Esc) dismisses with ``None``.
"""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import Input, LoadingIndicator

from mdview.ai import AiQueryError, edit_markdown
from mdview.ask_ai import _SelectionContext
from mdview.scroll_modal import ScrollableModalScreen


class EditInstructionScreen(ScrollableModalScreen):
    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(
        self,
        scope: str,
        *,
        claude: str,
        cwd: Path,
        label: str = "選択範囲",
    ) -> None:
        super().__init__()
        self._scope = scope
        self._claude = claude
        self._cwd = cwd
        self._label = label

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-input-dialog") as dialog:
            dialog.border_title = f"AIで編集 — {self._label}"
            yield _SelectionContext(
                self._scope_preview(), full=self._scope, id="edit-input-context"
            )
            yield Input(
                placeholder="編集の指示… 例: 表に直して / 校正して (Enterで実行, Escで閉じる)",
                id="edit-input-field",
            )
            loading = LoadingIndicator(id="edit-input-loading")
            loading.display = False
            yield loading

    def _scope_preview(self) -> str:
        text = " ".join(self._scope.split())
        if len(text) > 200:
            text = text[:200] + "…"
        return f"対象: {text}  （クリックで全文）"

    def on_mount(self) -> None:
        self.query_one("#edit-input-field", Input).focus()

    def scroll_region(self) -> ScrollableContainer:
        # No tall content here, but the base needs a region; point at the dialog.
        return self.query_one("#edit-input-dialog", Vertical)

    def action_dismiss(self) -> None:
        self.dismiss(None)  # cancelled → no edit

    def on_input_submitted(self, event: Input.Submitted) -> None:
        instruction = event.value.strip()
        if not instruction:
            return
        self._run_edit(instruction)

    @work(exclusive=True)
    async def _run_edit(self, instruction: str) -> None:
        input_widget = self.query_one("#edit-input-field", Input)
        loading = self.query_one("#edit-input-loading", LoadingIndicator)
        input_widget.disabled = True
        loading.display = True
        try:
            edited = await edit_markdown(
                self._scope,
                instruction,
                claude=self._claude,
                cwd=self._cwd,
            )
        except AiQueryError as e:
            self.notify(f"編集に失敗しました: {e}", severity="error")
            loading.display = False
            input_widget.disabled = False
            return
        self.dismiss(edited)
