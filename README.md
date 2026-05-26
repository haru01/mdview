# mdview

ターミナル上で Markdown を読みやすく表示する TUI ビューア。SVG・画像・Mermaid 図をインラインでレンダリングします。

## 特徴

- **読みやすい表示** — [Textual](https://textual.textualize.io/) ベースの TUI。見出しやテーブルに階層を付けたスタイリング。
- **画像のインライン表示** — PNG / JPG / GIF / WebP / BMP を端末内に描画。
- **SVG レンダリング** — `cairosvg` でラスタライズして表示。
- **Mermaid 図** — `mermaid` コードフェンスを図として描画（別途 `mmdc` が必要、後述）。
- **目次（TOC）** — トグルで表示し、ツリーをキーボードで辿れる。
- **リンク追跡** — 別の `.md` ファイルへのリンクを開き、`b` で戻れる。アンカー（`#section`）にも対応。
- **AI に質問（Ask AI）** — 本文をマウスで選択して `a` を押すと、選択範囲について `claude` に質問できる（別途 `claude` CLI が必要、後述）。
- **stdin 入力** — `mdview -` でパイプから読み込み。
- **非 TTY フォールバック** — パイプや CI など端末でない出力先には整形済みテキストを出力。

## インストール

[uv](https://docs.astral.sh/uv/) を使う場合（推奨）。リポジトリのルートで:

```sh
# どこからでも mdview コマンドを使えるようにする
uv tool install .

# 開発しながら使う場合は editable で
uv tool install --editable .
```

インストールせず都度実行する場合（プロジェクトディレクトリ内）:

```sh
uv run mdview README.md
```

## 使い方

```sh
mdview path/to/file.md      # ファイルを開く
cat notes.md | mdview -     # stdin から読み込む
gh pr view 123 | mdview -   # 他コマンドの出力をそのまま表示
mdview file.md | less       # 非 TTY 出力時は整形テキストを出力
```

stdin 入力時、相対パスの画像・リンクはカレントディレクトリ（CWD）を基準に解決します。

### キーバインド

| キー | 動作 |
| --- | --- |
| `j` / `↓` | 1 行下へスクロール |
| `k` / `↑` | 1 行上へスクロール |
| `Ctrl+d` / `Ctrl+u` | 半ページ下 / 上 |
| `g` / `G` | 先頭 / 末尾へ |
| `n` / `p` | 次 / 前の見出しへジャンプ |
| `t` | 目次（TOC）の表示切り替え |
| `b` / `←` | 直前のファイルへ戻る |
| `a` | 選択中のテキストについて AI に質問（Ask AI） |
| `h` / `?` | ヘルプパネルの表示切り替え |
| `q` / `Esc` | 終了 |

### Ask AI

本文をマウスでドラッグ選択してから `a` を押すとポップアップが開きます。質問を入力して `Enter` を押すと、開いているドキュメントの全文と選択した抜粋・質問が `claude -p` に渡され、回答が表示されます（`Esc` で閉じる）。

回答は開いているファイルの内容を文脈として生成されます（リポジトリ全体ではなく、そのドキュメントが対象）。

## 必要なもの

- Python 3.11 以上
- Mermaid 図を表示する場合は [`@mermaid-js/mermaid-cli`](https://github.com/mermaid-js/mermaid-cli) の `mmdc` が PATH 上に必要:

  ```sh
  npm install -g @mermaid-js/mermaid-cli
  ```

  `mmdc` が見つからない場合、Mermaid フェンスはコードブロックのまま表示されます。

- Ask AI（`a`）を使う場合は [`claude`（Claude Code）](https://claude.com/claude-code) CLI が PATH 上に必要。見つからない場合は `a` を押すとその旨を通知します。

## 開発

```sh
uv sync          # 依存関係をインストール
uv run pytest    # テスト実行
```
