# llm-wiki サポート設計

対象: `mdview` を Karpathy 式 LLM Wiki(`~/src/my-llm-wiki` のような Obsidian 互換の Markdown 知識ベース)のビューアとして使えるようにする。

## 背景

参考 wiki (`~/src/my-llm-wiki`) の Markdown は次の形式を持つ:

- **frontmatter**: 先頭の `---…---` YAML。`title` / `created` / `updated` / `type` / `tags: [a, b]` / `sources: [path]` / `confidence` など
- **`[[wikilink]]`**: `.md` 拡張子なしのファイル名(basename)参照。ツリー内のどこかにある同名ファイルを指す。`[[name|別名]]` / `[[name#見出し]]` 記法もある
- **タグ**: frontmatter の `tags` 配列

現状の mdview はこの 3 つを一切処理していない(frontmatter は `---` が水平線+見出しに崩れて表示、`[[]]` はただの文字列、タグは不可視)。本設計で 3 機能を追加する。

## 全体方針(isolation パターン)

純粋ロジックは新規モジュール **`wiki.py`**(framework-free, 単体テスト可)に集約。`app.py` は薄いフックと Textual ウィジェットだけ持つ。既存の `quickopen.list_viewable_files` / `search.compile_query` / grep・quick-open モーダルを再利用する。

`wiki.py` の純粋 API:

- `split_frontmatter(text) -> FrontmatterSplit` — 先頭 `---\n…\n---\n` を分離。`raw_prefix`(区切り含む原文, 無ければ `None`)、`meta`(dict, 無ければ空)、`body`(残り本文)を返す。frontmatter が無いテキストはそのまま body として返す(冪等)
- `parse_wikilinks(text) -> list[WikiLink]` — `[[target#anchor|alias]]` を抽出。各要素は `(start, end, target, anchor, alias)`
- `WikiIndex` — ルート配下を走査して構築。`by_stem: dict[str, list[Path]]`(basename 解決用)と `by_tag: dict[str, list[Path]]`(frontmatter tags 集計用)を持ち、`resolve(name) -> list[Path]` と `files_with_tag(tag) -> list[Path]` を提供。走査は `quickopen.list_viewable_files` を再利用し、各ファイルの frontmatter だけを読む

依存追加: **PyYAML**(frontmatter パース。日付・インラインリスト `[a, b]`・引用符付き値を正しく扱うため)。

## ① frontmatter を整形パネルで表示

### 核心的な設計判断: 本文と分離して別保持

frontmatter は**ソース文字列(`document.source`)からは剥がすが、prefix として別フィールドに保持**する。理由: AI 編集ループ・dirty 判定・`:w` はすべて `document.source` が「ディスク上のテキストと一致する」前提で動く。frontmatter を source に残すと崩れて描画され、source を書き換える(剥がす/リンク変換する)と編集ループがファイルを破壊する。

frontmatter は必ず連続した先頭ブロックなので、剥がしても本文の行番号が一定オフセットずれるだけ。往復再構成が安全に成立する:

- `on_mount` / `_load_file` / 外部リロード: raw を読む → `split_frontmatter` → **本文だけ**を既存の `_source_for`(diff 検出)に渡してレンダリング(`document.source` = 本文)。`self._frontmatter_raw`(区切り含む原文, または `None`)と `self._frontmatter_meta` を保持
- `_disk_baseline` は**本文側**で保持・比較 → dirty 判定・undo・AI 編集の行範囲計算はすべて本文座標で一貫。既存ロジック無改修
- `:w` 書き戻し時のみ `frontmatter_raw + document.source` を連結してディスクへ書く(frontmatter 復元)。stdin / transient view では従来どおり `:w` 無効

### パネル描画

`meta` から **Markdown blockquote に scaffold** して本文先頭に注入する(`diff_to_markdown` と同じ「モデル → Markdown 文字列」発想)。これで:

- 既存の Markdown レンダラ・theme.css スタイルをそのまま使える
- `tags` を `[learning](tag:learning)` リンク、`sources` を `[…](wiki:…)` リンクとして描画 → 既存のリンククリック経路(`on_markdown_link_clicked`)でそのままクリック可能

パネルは `_inject_frontmatter` パスで注入(他の `_inject_*` と同列。`_remove_injected_widgets` で再レンダリング時に除去)。theme.css で blockquote をパネル風(枠・淡い背景)に装飾。

## ② `[[wikilink]]` をクリック可能に

### ソースは書き換えず、レンダリング後の Content を加工

既存の 💡 section-insight マーカーと**同一パターン**を踏襲する:

- `set_content(base + marker)` 相当で Content を差し替え、clean な pre-marker Content を `_insight_base` 相当のフィールドに stash
- Content `@click` アクションでクリックを App へルーティング
- `get_selection` / `_search_text` をオーバーライドして、コピー/検索/AI には `[[…]]` 原文を返す(マーカーやリンク装飾を漏らさない)

ソース汚染ゼロなので編集ループと完全両立する。

実装:

- `_inject_wikilinks` パスを追加。`parse_wikilinks` で `[[…]]` を含む各 `MarkdownBlock`(段落・リスト項目・見出し・引用)の Content を、リンクスパン `[@click=app.wikilink('target','anchor')]alias[/]` に差し替え。`alias` 未指定なら `target` を表示
- `action_wikilink(target, anchor)` → `WikiIndex.resolve(target)`:
  - **1 件** → 既存の `_navigate_to(path, anchor)`(履歴付き)
  - **複数(曖昧)** → quick-open 風ピッカーで候補選択 → 選択を `_navigate_to`
  - **0 件(リンク切れ)** → スパンを別スタイル(`$error` 系の色 + 破線下線相当)で描画し、クリック時は「リンク切れ: name」を通知
- `[[name|alias]]`(別名)/ `[[name#heading]]`(見出しアンカー)対応。リンク切れ判定は注入時に `WikiIndex.resolve` を引いてスタイルを分岐

## ③ タグクリックで候補ファイル一覧

- frontmatter パネルの `tag:` リンククリック → `on_markdown_link_clicked` の `tag:` スキーム分岐 → `action_tag_files(tag)`
- 新規 `wiki_tag.py:TagFilesScreen`(`project_grep.py` / `quick_open.py` と同型の `Input` + `OptionList` モーダル)。`WikiIndex.files_with_tag(tag)` の結果を `quickopen.fuzzy_filter` で絞り込み、Enter で `dismiss` → `_navigate_to`
- `on_markdown_link_clicked` に `wiki:` / `tag:` スキーム分岐を追加(既存の `#anchor` / `http(s)` / 相対 md 判定の前段に置く)

## 新規 / 変更ファイル

新規:

- `wiki.py`(純粋: `split_frontmatter` / `parse_wikilinks` / `WikiIndex`)
- `wiki_tag.py`(`TagFilesScreen` — 薄い Textual ラッパ)
- `tests/test_wiki.py`(純粋モジュールの単体テスト)

変更:

- `app.py`:
  - frontmatter split 保持(`_frontmatter_raw` / `_frontmatter_meta`)と `on_mount` / `_load_file` / リロード / `:w` の連結
  - `_inject_frontmatter` / `_inject_wikilinks` パス追加、`_remove_injected_widgets` に対応
  - `on_markdown_link_clicked` に `wiki:` / `tag:` 分岐、`action_wikilink` / `action_tag_files`
  - `WikiIndex` のライフサイクル(ルート確定時に構築、キャッシュ)
- `theme.css`(frontmatter パネル / リンク切れの装飾)
- `help.py`(キー・機能説明)
- `pyproject.toml`(`pyyaml` 追加)
- `CLAUDE.md`(アーキテクチャ追記)

## テスト方針

- `wiki.py` は純粋関数として直接テスト:
  - `split_frontmatter` の往復(`raw_prefix + body == 原文`)、frontmatter 無し/空/壊れた区切りの冪等性
  - `parse_wikilinks` の各記法(素/別名/アンカー/複数)
  - `WikiIndex.resolve`(一意/曖昧/不在)と `files_with_tag`(集計・順序)
- app 統合は `app.run_test()` ピロットで:
  - wikilink クリック → 遷移、別名表示、アンカー、リンク切れ通知、曖昧時ピッカー
  - タグクリック → `TagFilesScreen` 表示 → 選択遷移
  - **frontmatter 付きファイルの `:w` 往復が原文(frontmatter 含む)を保持すること**(退行防止の要)
  - コピー/検索が wikilink 原文 `[[…]]` を返すこと

## 対象外(YAGNI)

- バックリンク一覧・知識グラフ可視化(将来の別 spec)
- wikilink からの新規ファイル作成(Obsidian の未作成リンク作成挙動)
- frontmatter の編集 UI(閲覧のみ。編集は本文の AI 編集ループ経由)
