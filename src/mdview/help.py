"""Popup (centered modal) keyboard-shortcut help.

`?` or `:h` opens this. The viewer has no permanent footer, so this is where the
key map is discoverable. The bindings list is hand-maintained here (rather than
derived from `App.BINDINGS`) so it can be grouped and labelled like a man page /
delta cheat-sheet; keep it in sync when bindings change.
"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer, VerticalScroll
from textual.widgets import Static

from mdview.scroll_modal import ScrollableModalScreen

# Theme accents (see theme.css): coral for section titles, green for keys.
_TITLE_STYLE = "bold #d97757"
_KEY_STYLE = "bold #4ebf71"

# (section title, [(keys, description), ...]) in display order. Mirrors the
# final key map in the design; update alongside MdViewerApp.BINDINGS.
HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "移動",
        [
            ("j ↓ / k ↑", "行送り"),
            ("d / u", "半画面 送り/戻し"),
            ("f / b", "1画面 送り/戻し"),
            ("g < / G >", "先頭 / 末尾"),
            ("S-→ / S-←", "横スクロール（イベントフロー）"),
        ],
    ),
    (
        "検索",
        [
            ("/", "文書内を検索"),
            ("n / N", "次 / 前マッチ"),
            ("^G  :grep", "プロジェクト全体を検索"),
        ],
    ),
    (
        "構造",
        [
            ("Space / S-Space", "次 / 前（見出し、diff ではファイル+ハンク）"),
            ("] / [", "次 / 前見出し（diff ではファイル）"),
            ("^] / ^[", "次 / 前 見出し2（## セクション）"),
            ("} / {", "次 / 前ハンク（diff）"),
            ("t", "目次"),
            ("e", "ファイルツリー 開閉"),
            ("^O  :e", "ファイル/diff を開く（あいまい検索）"),
            ("l  :log", "コミット履歴を開く"),
        ],
    ),
    (
        "リンク",
        [
            ("Backspace ←", "履歴を戻る"),
        ],
    ),
    (
        "選択・AI",
        [
            ("v / V", "選択を拡大 / 縮小"),
            ("y", "選択をコピー"),
            ("h", "選択を AI に質問 (回答後も続けて質問可)"),
            ("w", "選択を AI で編集"),
            ("💡", "見出しの解説（クリック）"),
        ],
    ),
    (
        "コマンド・その他",
        [
            (":", "コマンドライン"),
            (":q  q", "終了（未保存なら確認）"),
            (":w", "保存"),
            (":wq", "保存して終了"),
            (":q!", "保存せず終了"),
            (":undo", "直前の AI 編集を取り消し"),
            (":log", "コミット履歴を開く (--log)"),
            (":h  ?", "このヘルプ"),
            ("Esc", "キャンセル（終了しない）"),
        ],
    ),
]


def render_help() -> Table:
    """Build the grouped key-map as a Rich grid (keys ｜ description)."""
    grid = Table.grid(padding=(0, 3))
    grid.add_column(justify="left", no_wrap=True)
    grid.add_column(justify="left")
    for i, (title, rows) in enumerate(HELP_SECTIONS):
        if i:
            grid.add_row("", "")  # blank spacer between sections
        grid.add_row(Text(title, style=_TITLE_STYLE), "")
        for keys, desc in rows:
            grid.add_row(Text(f"  {keys}", style=_KEY_STYLE), Text(desc))
    return grid


class HelpScreen(ScrollableModalScreen):
    """Centered modal listing the keyboard shortcuts (scrollable with the same
    movement keys as the main view; see ScrollableModalScreen)."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
        ("q", "dismiss", "Close"),
        ("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog") as dialog:
            dialog.border_title = "ショートカット"
            with VerticalScroll(id="help-body"):
                yield Static(render_help())

    def scroll_region(self) -> ScrollableContainer:
        return self.query_one("#help-body", VerticalScroll)

    def action_dismiss(self) -> None:
        self.dismiss()
