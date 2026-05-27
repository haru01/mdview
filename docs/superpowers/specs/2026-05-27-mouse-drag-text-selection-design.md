# マウスドラッグによる任意範囲テキスト選択

- 日付: 2026-05-27
- 対象: `mdview`(Textual ベースの TUI Markdown ビューア)
- 変更範囲: `src/mdview/app.py` のみ + テスト追加

## 背景と問題

現状、ビューア内でマウスをドラッグしても任意の範囲(段落内の一語句など)を選択できない。
原因は「ドラッグ機能が無い」のではなく、既存のクリック=ブロック選択がドラッグ結果を握りつぶしていることにある。

- ドラッグによる文字選択は Textual 本体が画面レベルでサポートしている
  (`screen.py` の `MouseDown` → `MouseMove`(`_selecting`) → `MouseUp`)。既定で
  `App.ALLOW_SELECT` / `Screen.allow_select` / `Widget.allow_select` はすべて `True`。
- ところが Textual は「`MouseDown` と `MouseUp` が同じウィジェット上」で起きると、
  ドラッグ移動量に関係なく `Click` を発火させる(`app.py` の MouseUp 処理、`mouse_up_widget is mouse_down_widget` の分岐)。
- `mdview` の `App.on_click`(`app.py:772`)は、クリックのたびに無条件で
  「ブロック単位のセマンティック選択」を適用する(`_apply_scope` が `screen.selections` を上書き)。
- 結果、段落内をドラッグして範囲選択しても、指を離した瞬間に発火する `Click` が
  ブロック全体の選択で上書きしてしまう。これがドラッグで任意範囲を選べない主因。

(補足: ブロックをまたぐドラッグは MouseUp の着地ウィジェットが押下ウィジェットと異なるため
`Click` が発火せず、本体の選択が残ることがある。ユーザーが最もよく行う「段落内の語句選択」が
握りつぶされるため、体感として「ドラッグできない」となる。)

## 目標 / 非目標

### 目標
- ドラッグで任意範囲のテキストを選択できるようにする。
- 既存の挙動を維持する:
  - 単発クリック = ブロック全体を選択、同一ブロック再クリックで 1 段階拡大。
  - `v` / `V` キーによるセマンティック選択の梯子(expansion ladder)。
  - `Esc`(`action_cancel`)で選択解除し梯子をリセット。
  - Ask AI(`h`)は `screen.get_selected_text()` 経由なので、ドラッグで選んだ範囲も自動的に対象になる。

### 非目標(YAGNI)
- ダブルクリックでの単語選択・トリプルクリックでの段落/全選択(Textual 本体機能の上書き是正)。今回の要望外。
- 選択範囲のクリップボードコピー機能の追加。
- クリック=ブロック選択そのものの廃止・変更。

## 設計(承認済みアプローチ A)

`mdview` 側でクリックとドラッグを区別し、ドラッグ時は `on_click` でフレームワークの
自由選択を上書きしないようにする。判定方法は Textual 本体がクリック/ドラッグを区別する方法
(押下位置と離した位置の `screen_offset` 比較、`screen.py` の `_mouse_down_offset == event.screen_offset`)
と同一にし、最小・低リスクに留める。

変更は `src/mdview/app.py` のみ、おおよそ 15 行程度。

### 1. 状態の追加(`__init__`)
押下時のスクリーン座標を保持するフィールドを追加する。
```python
self._mouse_down_offset: Offset | None = None
```
(`textual.geometry.Offset` を import。)

### 2. 押下位置の記録(`on_mouse_down`)
```python
def on_mouse_down(self, event: events.MouseDown) -> None:
    self._mouse_down_offset = event.screen_offset
```
`MouseDown` はポインタ下のウィジェットからバブルして App に届く(既存の `on_click` が App
レベルで動作している事実と同じ経路)。

### 3. `on_click` のガード追加
`on_click` の冒頭で、Click の `screen_offset` が押下位置と異なれば「ドラッグ」と判定し、
本体の自由選択を残したまま return する。同一なら従来どおりセマンティック選択を行う。
```python
def on_click(self, event: events.Click) -> None:
    # 押下位置と離した位置が異なる = ドラッグ。フレームワークの自由選択を
    # そのまま残し、セマンティックの梯子はリセットして次の v/クリックを
    # 最小ブロックから始められるようにする。
    if self._mouse_down_offset is None or event.screen_offset != self._mouse_down_offset:
        self._reset_selection_state()
        return
    # 以下、従来どおり: クリック = ブロック単位のセマンティック選択
    leaf = find_leaf_block(event.widget)
    ...
```

### 4. 影響しないもの(確認事項)
- `v` / `V`(`action_expand_selection` / `action_shrink_selection`): ドラッグ後は梯子が
  リセットされているため、`v` は `_first_visible_block()` から新規に始まる(自然な挙動)。
- `Esc`(`action_cancel`): 既に `screen.clear_selection()` + `_reset_selection_state()` を行うため
  ドラッグ選択も解除できる。変更不要。
- Ask AI: `screen.get_selected_text()` はセマンティック選択でもドラッグ選択でも同じ API なので
  追加対応不要。

## 判定の根拠(座標比較の妥当性)

ターミナルのセル座標は整数で離散的なので、「押下セルと離したセルが同一」= 移動なし = クリック、
「異なる」= ドラッグ、と扱える。閾値計算は不要で、Textual 本体の判定(`_mouse_down_offset == event.screen_offset`)
と一致するため挙動が一貫する。`_mouse_down_offset` が `None`(押下を捕捉できない異常系)の場合は
安全側に倒してクリック扱いとせず、ドラッグ扱い(= 上書きしない)とする。

## テスト

`tests/test_app.py` に Pilot ベースのテストを追加する。

1. **ドラッグ時は握りつぶさない**: `on_mouse_down` 相当で押下オフセットを記録した状態で、
   別オフセットの `Click` を流し、`on_click` がセマンティック選択を適用しない
   (`_sel_scopes` がリセットされ、`screen.selections` がブロック全体にならない)ことを確認。
2. **クリック時は従来どおり**: 同一オフセットの `Click` でブロック単位のセマンティック選択が
   適用されることを確認(セマンティック選択が始まった状態 = `_sel_scopes is not None`)。
3. **回帰**: 既存の選択・検索・ナビゲーション関連テストが引き続き通ること
   (`uv run pytest`)。

可能なら、Pilot で実際に `MouseDown` → `MouseMove` → `MouseUp` → `Click` を流して
フレームワークの自由選択が残ることを End-to-End で確認するテストも追加する
(Pilot のマウス API で実現可能な範囲で)。

## リスク

- 低リスク。変更は単一ファイル・少行数で、既存の選択 API(`screen.selections` /
  `get_selected_text` / `clear_selection`)に依存し、新しい依存は無し。
- ターミナル/環境によってはマウストラッキング自体が無効な場合があるが、これは本変更の範囲外
  (本体の既定動作に従う)。
