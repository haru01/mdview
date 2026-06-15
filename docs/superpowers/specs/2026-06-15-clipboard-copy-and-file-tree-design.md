# 設計: 選択範囲のクリップボードコピー(`y`)とファイルツリー サイドバー

日付: 2026-06-15

## 背景

`mdview` は単一ファイル専用の読み取り特化 Markdown TUI ビューア。選択ラダー
(`v`/`V`)・Ask AI(`h`)・AI 編集(`w`)で「選択範囲」を扱う基盤は完成しているが、
選択テキストをそのままクリップボードへ出す手段がない。また `cli.py` の引数は
単一 `file` のみで、ディレクトリやノート集をまたいで読む手段がない。

本設計は次の 2 機能を追加する:

1. 選択範囲のクリップボードコピー(`y`)
2. ディレクトリ/ファイルツリー サイドバー(`e` でトグル、`mdview <dir>` で起動)

## 機能1: 選択範囲のクリップボードコピー(`y`)

### 動作

- 新キーバインド `y` → `action_copy_selection`。
- 現在の選択範囲の「クリーンテキスト」を取得し、`App.copy_to_clipboard`
  (OSC52)へ渡す。成功時に `「{n} 文字をコピーしました」` を通知。
- 選択範囲がなければ `「選択範囲がありません」` と通知し、それ以外は何もしない
  (Ask AI / 編集と同じく選択ベースで一貫させる)。
- テキスト取得は Ask AI / 編集ループと**同じ選択基盤**を再利用する。各ウィジェットの
  `get_selection`(`DiffHunk` は unified diff、`EventFlow` は元 DSL、見出しは
  マーカー除去済みテキスト)を経由するため、出口だけを足す形になる。

### コンポーネント

- `app.py`
  - `BINDINGS` に `Binding("y", "copy_selection", "Copy", show=True)` を追加。
  - `action_copy_selection` を追加。選択テキスト取得 → 空なら通知して return →
    `self.copy_to_clipboard(text)` + 通知。
  - 選択テキスト取得は、Ask AI が現在使っている取得経路と同一のものを呼ぶ
    (実装時に `action_ask_ai` の取得箇所を確認して共通ヘルパー
    `_current_selection_text() -> str` に切り出し、Ask AI / コピー双方から使う)。

### テスト

- `_current_selection_text` の純粋な振る舞い(選択なし → `""`、全選択 → 本文)を
  pilot で確認。
- pilot: 全選択 → `y` → `app.clipboard` に本文が入る。未選択 → `y` → クリップボード
  不変かつ通知が出る。

## 機能2: ディレクトリ/ファイルツリー サイドバー

### 起動・UX

- `mdview docs/`(ディレクトリ引数)でサイドバー表示つき起動。`cli.py` が
  `path.is_dir()` を判定し、`MdViewerApp(root_dir=path, md_path=initial)` を構築。
- 単一ファイル閲覧中も `e`(explorer)でサイドバーを開閉。開くとツリーにフォーカス。
- ツリー内操作: `j/k`・矢印で移動、`Enter` で選択ファイルを viewer に開きフォーカスを
  viewer へ戻す。`Tab` でペイン間フォーカス切替、`Esc` / `e` でサイドバーを閉じて
  viewer にフォーカスを戻す。
- ディレクトリ起動時の初期表示: トップに `README.md` があれば開く → なければ最初の
  `.md`(`sorted()` 順)→ どちらもなければ viewer は空で
  `「左のツリーからファイルを選択してください」` を表示。
- ディレクトリ + 非 TTY は単一ドキュメント化できないため、`cli.py` で
  `mdview: {dir}: is a directory` を stderr に出して `exit(1)`。

### ツリー内容

- Textual の `DirectoryTree` を継承した `_MdTree` を作り、`filter_paths` で
  ディレクトリと拡張子 `.md / .markdown / .diff / .patch` のファイルのみを残す。
  再帰はツリーの遅延展開で標準対応。
- 表示判定は純粋関数 `is_viewable(path: Path) -> bool` に切り出し、`filter_paths` は
  これを使う(直接テスト可能にするため)。

### `_load_file` の diff 対応

- 現状 `_load_file` は常に Markdown として描画する。ツリーに `.diff`/`.patch` を
  出す以上、それらを開いたときも delta 表示にする。
- `_load_file` で読み込んだテキストが `looks_like_diff` なら、`parse_diff` →
  `diff_to_markdown` で scaffold したテキストを描画し `self._diff_files` を更新。
  そうでなければ `self._diff_files = None` にして従来どおり Markdown 描画。
- これによりリンク追跡で `.diff` を開いた場合も含めて一貫する。

### レイアウト/組み込み

- `compose` の viewer を `Horizontal` で包み、左に `_MdTree(id="sidebar")`、右に
  `_MdViewer` を置く。cmdline-bar はボトムドックなので DOM 順の影響はない。
  `query_one(MarkdownViewer)` は引き続き一意に解決できる。
- サイドバーは `theme.css` で固定幅(例 30)・左寄せ。初期表示状態は `root_dir` の
  有無で決める(`display` をトグル)。
- ファイル選択は既存の `_navigate_to`(履歴つき)に委譲して再利用する。

### コンポーネント

- `cli.py`: ディレクトリ引数のハンドリング(初期ファイル決定、非 TTY エラー)。
- `app.py`:
  - `MdViewerApp.__init__` に `root_dir: Path | None = None` を追加。
  - `compose` を `Horizontal` 包みに変更、`_MdTree` を yield。
  - `action_toggle_sidebar`(`e`)、ツリーの `FileSelected` ハンドラ、フォーカス
    切替を追加。`_load_file` の diff 対応。
  - `BINDINGS` に `Binding("e", "toggle_sidebar", "Files", show=True)`。
- `filetree.py`(新規・純粋): `is_viewable(path)` と初期ファイル決定
  `initial_file(root: Path) -> Path | None`。Textual 非依存でテスト可能にする。
- `_MdTree`(`app.py` または `filetree` の薄い Textual ラッパ): `DirectoryTree`
  継承、`filter_paths` が `is_viewable` を使う。

### テスト

- `filetree.py` の `is_viewable` / `initial_file` を直接テスト
  (`.md` 受理、`.txt` 拒否、`README.md` 優先、空ディレクトリ → None など)。
- pilot: `root_dir` 付き起動でツリーが存在、`README.md` が初期表示される。
- pilot: ノード選択で viewer が切り替わる(履歴に積まれる)。
- pilot: `e` でサイドバー開閉、開くとツリーにフォーカス。
- pilot: `.diff` ファイルを開くと `DiffHunk` が注入される(diff 対応)。

## スコープ外(YAGNI)

- ディレクトリ横断 grep 検索。
- タブ/複数同時オープン。
- ツリーからのファイル作成・リネーム・削除。
- 設定ファイルによるサイドバー幅やデフォルト挙動のカスタマイズ。

## 受け入れ基準

- 全選択して `y` でシステムクリップボードに本文が入る。未選択時は no-op + 通知。
- `mdview <dir>` でツリー付き起動し、`README.md`(あれば)が初期表示される。
- 単一ファイル閲覧中に `e` でツリーを開閉でき、ツリーからファイルを開ける。
- ツリー/リンクから `.diff` を開くと delta 表示になる。
- 既存テストがすべて通り、上記の新規テストが通る。
