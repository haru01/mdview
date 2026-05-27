# TOC をポップアップ（中央モーダル）化する

- 日付: 2026-05-27
- 状態: 実装済み（`src/mdview/toc.py`, `app.py`, `theme.css`, `tests/test_app.py`）

## 背景 / 問題

`t` を押すと左ドックの目次（TOC）サイドバーが開く。`theme.css` で `MarkdownTableOfContents` は `width: 30%; min-width: 20; max-width: 50` に制限され、内側の Textual `Tree` はノードのラベルを**折り返さず available width で切り捨てる**。

diff 表示（`gh pr diff | mdview -` など）では見出しが長いファイルパス（例: `openspec/changes/add-cell-context-menu/design.md`）や `@@ -0,0 +1,177 @@` のようなハンクヘッダになるため、このサイドバー幅では文字が切れて読めない。

## ゴール

- `t` で**中央モーダルの TOC** を開き、広い幅（画面の 80%）で見出し全文を読めるようにする。特に diff のファイルパス / ハンクを判別できること。
- モーダル内で見出しを選び、その位置へジャンプしてモーダルを閉じられること。

## 非ゴール（YAGNI）

- ラベルの折り返し・横スクロールは実装しない（80% 幅で通常の diff パスはほぼ収まる。超長パスは切れたままで許容）。
- ドック型サイドバー表示モードの存続（トグルでサイドバーに戻す等）はしない。ポップアップに一本化する。

## 設計

### 採用アプローチ

既存の `MarkdownTableOfContents` ウィジェット（ツリー構造・番号・ガイド線・選択メッセージ）を、新規 `ModalScreen` に載せて中央表示する。番号付けや選択処理を再利用でき、本プロジェクトの `ModalScreen` パターン（`AskAiScreen` / `ImageZoomScreen`）と一致する。独自 Tree / OptionList を組む案は、再実装コストや階層喪失のため採らない。

### 挙動

- `t`: `TocScreen` モーダルを開く。
- モーダル内:
  - `↑/↓` および `j/k` でツリーのカーソル移動。
  - `Enter`（またはクリック）で、その見出しの位置へメイン本文をスクロールし、モーダルを閉じる。
  - `Esc` / `q` / `t` で閉じる。

### コンポーネント

新規ファイル `src/mdview/toc.py`:

```
class TocScreen(ModalScreen):
    BINDINGS = [escape→dismiss, q→dismiss, t→dismiss, j→cursor_down, k→cursor_up]

    def __init__(self, viewer: MarkdownViewer, toc_data): ...
        # viewer: 選択時にスクロールさせる対象。
        # toc_data: 現ドキュメントの TOC データ（level, name, block_id のリスト）。

    def compose(self):
        with Container(id="toc-dialog"):
            yield MarkdownTableOfContents(self._viewer.document)

    def on_mount(self):
        toc = self.query_one(MarkdownTableOfContents)
        toc.table_of_contents = self._toc_data   # ツリー再構築をトリガ
        call_after_refresh → 内側 Tree を focus（j/k・↑/↓ が即効くように）

    def on_markdown_table_of_contents_selected(self, message):
        block = self._viewer.query_one(f"#{message.block_id}", MarkdownBlock)
        self._viewer.scroll_to_widget(block, top=True)
        message.stop()
        self.dismiss()

    def action_cursor_down/up(self):
        self.query_one(Tree).action_cursor_down/up()  # j/k をツリーに橋渡し
```

### `app.py` の変更

- `BINDINGS`: `Binding("t", "open_toc", "TOC", show=True)`（`toggle_toc` から改名）。
- `action_toggle_toc` → `action_open_toc`:
  - `viewer = self.query_one(MarkdownViewer)`
  - `toc_data = viewer.query_one(MarkdownTableOfContents).table_of_contents`
  - `toc_data` が空/未取得なら何もしない（防御）。
  - `self.push_screen(TocScreen(viewer, toc_data))`
- `_focus_toc` は不要になるため削除（focus はモーダル側で行う）。
- `_MdViewer.compose` は**据え置き**。`MarkdownTableOfContents` は viewer 内に残す（Textual の `MarkdownViewer._on_markdown_table_of_contents_updated` が `query_one(MarkdownTableOfContents)` でデータを書き込むため。除去するとそのハンドラが壊れる）。`show_table_of_contents=False` のまま非表示のデータ保持役とする。

### データフロー

1. ドキュメント load → `Markdown.TableOfContentsUpdated` 発火 → viewer が内部の（非表示）`MarkdownTableOfContents` に反映（既存挙動）。
2. `t` → app が viewer 内 TOC ウィジェットから `table_of_contents` データを読み、`TocScreen` に渡す。
3. `TocScreen` が自前の `MarkdownTableOfContents` を生成し、同データで構築。
4. ノード選択 → `Markdown.TableOfContentsSelected(block_id)` 発火 → `TocScreen` が受け、メイン viewer の `#block_id` 要素へ `scroll_to_widget(top=True)` → `dismiss()`。

注意点: モーダルの TOC が出す `TableOfContentsSelected` は viewer の子孫ではないため、viewer の既存 `_on_markdown_table_of_contents_selected` は発火しない。`TocScreen` で明示的に処理する。

### スタイル（theme.css）

- 既存の `MarkdownTableOfContents { width:30%; min-width:20; max-width:50 }` はサイドバー前提の値。ポップアップではモーダル側の指定で上書きされるよう、`#toc-dialog` 配下のセレクタで幅を与える。サイドバーは使わなくなるが、当該ルールは害がなければ残置（整理は任意）。
- 追加:
  - `TocScreen { align: center middle; background: $surface 60%; }`
  - `#toc-dialog { width: 80%; height: 80%; border: round $orange; background: $panel; }`（タイトル「目次」を border title で表示）
  - `#toc-dialog MarkdownTableOfContents { width: 1fr; height: 1fr; }`
  - 縦に溢れる場合は内側 Tree がスクロール（Tree は縦スクロール可）。

### テスト（tests/test_app.py、必要なら tests/test_toc.py）

- `t` 押下で `TocScreen` が push される（`isinstance(app.screen, TocScreen)`）。
- `TocScreen` 内の `Tree` に、現ドキュメントの見出しノードが存在する（diff フィクスチャでファイル/ハンク見出しが入る）。
- モーダルのノードを選択すると、メイン viewer がその位置へスクロールし（`scroll_y` 変化 もしくは対象ブロックが可視域）、`TocScreen` が pop される。
- `Esc` で `TocScreen` が閉じる。
- 既存の diff 着色回帰テスト（`test_diff_fence_colour_survives_toc_toggle`, line 811 付近で `press("t")`）は、`t` がモーダルを開く挙動に変わっても着色は維持されるため**そのまま通る想定**。コメント文言（「show TOC → ...」）は実態に合わせて更新。

## リスク / 留意

- **TOC データ取得タイミング**: load 直後に `t` を押した場合、`TableOfContentsUpdated` が反映済みか。テストでは `pilot.pause()` を複数回挟む。空データ時は `action_open_toc` で no-op。
- **80% 幅でも超長パスは切れる**: 非ゴールとして許容。
- **`MarkdownTableOfContents` の二重存在**: viewer 内（データ保持・非表示）とモーダル内（表示）に各 1 つ。両者とも同じ document を参照するが、表示するのはモーダルのみで競合しない。
