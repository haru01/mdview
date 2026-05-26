# Mermaid を非 TTY 出力でも図としてレンダリングする

- Date: 2026-05-26
- Status: Approved (pending implementation)

## 背景

`mdview` は TUI モードでは `app.py::_inject_mermaid` が ` ```mermaid` フェンスを `mmdc` で SVG にし、`cairosvg` で PNG にして `textual_image.Image` ウィジェットに差し替えている。

一方、stdout がパイプされる非 TTY モード (`render.py::print_markdown`) では Markdown を rich にそのまま渡すだけで、Mermaid フェンスはコードブロックのまま流れる。`mdview` の主な消費者の 1 つである Claude Code は stdout を読み取って表示するため、Mermaid 図が見えない。

## ゴール

非 TTY モードでも Mermaid を図としてレンダリングし、Markdown 中の画像参照 (`![](<png path>)`) に置換して出力する。これにより、Claude Code が画像パスを拾えるようになる。TUI 側は既存実装のままとし、動作確認のみ行う。

## ノンゴール

- ターミナル画像プロトコル (Kitty/iTerm2 inline images) 対応
- ASCII アート化
- README やセットアップ手順の更新 (別タスク)
- `mmdc` 以外のレンダラ対応 (mermaid.ink, Playwright 等)
- TUI 側の機能追加

## 設計

### `render.py` の新しい振る舞い

`print_markdown(path: Path)` を以下の 3 段に分ける:

1. **読み込み:** `path.read_text(...)` で Markdown ソースを取得。
2. **Mermaid 前処理:** ソース文字列中の Mermaid フェンスを抽出。`mmdc` が PATH にあれば、各フェンスを SVG → PNG にレンダリングして一時ディレクトリに保存し、フェンス全体を `![](<png 絶対パス>)` に置換。レンダリングに失敗したフェンスは元のまま残す。`mmdc` が無ければ前処理をスキップ (現状の動作)。
3. **出力:** 置換後の Markdown を `Console(...).print(Markdown(...))` で stdout に出力。

### Mermaid フェンスの検出

GitHub Flavored Markdown のフェンスに合わせる:

- 行頭が 3 個以上の `` ` `` または `~` で始まり、info string が `mermaid` (空白許容、大文字小文字区別なし)。
- 同じ文字・同じ長さ以上の閉じフェンスまでを 1 ブロックとする。
- インデント付きコードブロック (4 スペース) は対象外。
- 簡潔さのため、正規表現ベースで実装する。複雑なケース (フェンス内にネストされた擬似フェンス等) は実用上ほぼ存在しないので考慮しない。

### 一時ファイル管理

- `tempfile.TemporaryDirectory(prefix="mdview-")` を `print_markdown` のローカルで作る。
- `atexit.register(tempdir.cleanup)` で登録し、プロセス終了まで PNG を残す (Claude Code が読み取り終わるまで保持するため)。
- PNG ファイル名はソースコードの SHA-1 先頭 12 桁を使う (TUI 側と同じ規約)。

### 既存コードとの共有

- `mermaid.py::render_mermaid`, `mermaid.py::find_mmdc` をそのまま再利用。
- `svg.py::rasterize_svg` も再利用 (SVG → PNG)。
- TUI 側 (`app.py::_render_mermaid_fence`) と概ね同じ処理だが、出力先が「Markdown テキストへの埋め込み」である点が違う。共通化はせず、シンプルに別関数で書く。

### エラー処理

- `MermaidRenderError` / `SvgRenderError` は個別フェンス単位で catch して、その 1 ブロックだけ元のまま残す。他のフェンスや出力全体には影響しない。
- `mmdc` 自体が無いときは静かにスキップ (TUI 側と同じ挙動)。

### ピクセル幅

- 非 TTY ではターミナル幅が分からない。固定値 `1600px` (TUI 側のデフォルト相当) を使う。

## テスト

新規ファイル: `tests/test_render.py`

- 既存の `tests/test_mermaid.py::_fake_mmdc` パターンと同じく、PATH を差し替える方式で偽 `mmdc` を用意する。
- `monkeypatch.setenv("PATH", ...)` で偽 `mmdc` を見せた状態で `print_markdown` を呼び、`capsys` で stdout をキャプチャ。
- アサーション:
  1. Mermaid フェンスが含まれた Markdown を渡すと、stdout に `mermaid-` で始まる PNG パスへの画像参照が現れる
  2. その PNG ファイルが実在する
  3. `mmdc` が PATH に無い (空 PATH) ときは Mermaid フェンスがそのまま stdout に残る
  4. Mermaid フェンス以外のコードブロック (` ```python` 等) は無変更で残る

既存テストの修正は不要。

## 実装順序

1. `render.py` のリファクタ + Mermaid 前処理関数追加
2. `tests/test_render.py` 追加 (前処理関数をユニットテスト + `print_markdown` を統合的にテスト)
3. ローカルで `mmdc` をインストール (`npm i -g @mermaid-js/mermaid-cli`) して手動確認
4. TUI 側の動作確認 (`mdview` で Mermaid を含む `.md` を開いて図が出ることを確認)
