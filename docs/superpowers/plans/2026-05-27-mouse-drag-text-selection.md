# マウスドラッグによる任意範囲テキスト選択 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ビューア内でマウスをドラッグして任意範囲のテキストを選択できるようにする(段落内の語句選択など)。

**Architecture:** ドラッグ選択機能は Textual 本体が画面レベルで既にサポートしている。`App.on_click`(`app.py:772`)がクリックのたびに無条件で「ブロック単位のセマンティック選択」を適用し、ドラッグ後に発火する `Click` がその自由選択を上書きしているのが原因。`on_mouse_down` で押下時のスクリーン座標を記録し、`on_click` で「離した位置と押下位置が異なる=ドラッグ」のときはセマンティック選択を適用せず early-return することで、本体のドラッグ選択を残す。判定は Textual 本体のクリック/ドラッグ判定(`screen.py` の `_mouse_down_offset == event.screen_offset`)と同じ座標比較を用いる。

**Tech Stack:** Python 3.11+, Textual 8.2.7, uv, pytest(Pilot ベースの非同期UIテスト)。

---

## File Structure

- `src/mdview/app.py`(Modify): `MdViewerApp` に押下座標の記録(`on_mouse_down`)と、`on_click` 冒頭のドラッグ判定ガードを追加。`from textual.geometry import Offset` を追加。
- `tests/test_app.py`(Modify): ドラッグ時に自由選択が上書きされないこと、クリック時は従来どおりセマンティック選択になることを検証する 2 テストを追加。

変更は単一ファイルのロジック追加(約15行)+テスト。新規ファイル・新規依存は無し。

---

## Task 1: クリックとドラッグを区別し、ドラッグ選択を上書きしない

**Files:**
- Modify: `src/mdview/app.py`(import 追加、`MdViewerApp.__init__` の選択状態定義付近 `app.py:160` 周辺、`on_click` `app.py:772`)
- Test: `tests/test_app.py`(末尾に 2 テスト追加)

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_app.py` の末尾に以下 2 テストを追加する(ファイル先頭の既存 import に加え、テスト内で必要なものはテスト内 import で補う。既存テストと同じく `asyncio.run(driver())` 形式)。

```python
def test_drag_selection_is_not_overwritten_by_click() -> None:
    """ドラッグ(押下位置≠離した位置)の自由選択を on_click が上書きしないこと。"""
    import asyncio

    from textual.events import Click
    from textual.selection import Selection
    from textual.widgets import MarkdownViewer
    from textual.widgets._markdown import MarkdownParagraph

    async def driver() -> None:
        app = MdViewerApp(content="# Title\n\nHello world paragraph for selection.\n")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            para = next(iter(viewer.document.query(MarkdownParagraph)))

            # 押下位置を実イベントで記録(on_mouse_down が配線されている確認も兼ねる)
            await pilot.mouse_down(para, offset=(0, 0))
            down = app._mouse_down_offset
            assert down is not None, "on_mouse_down should record the press offset"

            # ドラッグが作った細かい選択を模した番兵を置く
            sentinel = {para: Selection((0, 0), (0, 5))}
            app.screen.selections = sentinel
            app._sel_scopes = None

            # ドラッグ終了時に発火する Click を、押下位置とは別のセルで流す
            click = Click(
                widget=para,
                x=0,
                y=0,
                delta_x=0,
                delta_y=0,
                button=0,
                shift=False,
                meta=False,
                ctrl=False,
                screen_x=down.x + 5,
                screen_y=down.y,
                chain=1,
            )
            app.on_click(click)
            await pilot.pause()

            # 自由選択が残り、セマンティックの梯子は始まっていない
            assert app.screen.selections == sentinel, (
                "a drag's freeform selection must survive the trailing Click"
            )
            assert app._sel_scopes is None, "drag must not start the semantic ladder"

    asyncio.run(driver())


def test_stationary_click_still_selects_block() -> None:
    """ドラッグなしの単発クリックは従来どおりブロック単位のセマンティック選択になること。"""
    import asyncio

    from textual.widgets import MarkdownViewer
    from textual.widgets._markdown import MarkdownParagraph

    async def driver() -> None:
        app = MdViewerApp(content="# Title\n\nHello world paragraph for selection.\n")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            para = next(iter(viewer.document.query(MarkdownParagraph)))

            # pilot.click は MouseDown→MouseUp→Click を同一オフセットで送る = 静止クリック
            await pilot.click(para, offset=(2, 0))
            await pilot.pause()

            assert app._sel_scopes is not None, "a stationary click should start a selection"
            assert app.screen.get_selected_text(), "the clicked block's text should be selected"

    asyncio.run(driver())
```

- [ ] **Step 2: テストを実行して失敗を確認する**

Run: `uv run pytest tests/test_app.py::test_drag_selection_is_not_overwritten_by_click tests/test_app.py::test_stationary_click_still_selects_block -v`

Expected:
- `test_drag_selection_is_not_overwritten_by_click` は FAIL(`app._mouse_down_offset` 属性がまだ無いため `AttributeError`。実装後はパス)。
- `test_stationary_click_still_selects_block` は現状の `on_click` でも PASS する可能性が高い(回帰ガード)。少なくとも 1 件が FAIL すること。

- [ ] **Step 3: `app.py` に import を追加する**

`src/mdview/app.py` の import 群(`from textual.css.query import NoMatches` の直後)に追加:

```python
from textual.geometry import Offset
```

- [ ] **Step 4: `__init__` に押下座標フィールドを追加する**

`src/mdview/app.py` の `MdViewerApp.__init__` 内、セマンティック選択状態を定義している箇所(`self._sel_anchor: Widget | None = None` の直前、`app.py:160` 付近)に追加:

```python
        # マウス押下時のスクリーン座標。on_click でクリック(押下位置と一致)と
        # ドラッグ(不一致)を区別するために使う。ドラッグ時はフレームワークの
        # 自由選択を残したいので、on_click はセマンティック選択を適用しない。
        self._mouse_down_offset: Offset | None = None
```

- [ ] **Step 5: `on_mouse_down` を追加し、`on_click` にドラッグ判定ガードを入れる**

`src/mdview/app.py` の既存 `on_click`(`app.py:772`)を、直前に `on_mouse_down` を足したうえで次のように書き換える(ガード以降の本体は既存のまま):

```python
    def on_mouse_down(self, event: events.MouseDown) -> None:
        # 押下位置を覚えておき、on_click でクリック/ドラッグを判別する。
        # 本体のドラッグ選択は Screen 側で処理されるので、ここでは記録のみ。
        self._mouse_down_offset = event.screen_offset

    def on_click(self, event: events.Click) -> None:
        """Mouse-driven semantic selection.

        The first click on a block selects it; clicking the same block again
        expands one rung along the Markdown structure. Clicking a different
        block restarts the ladder there. (A stationary click clears any drag
        selection in the framework's MouseUp handler first; we then set ours.)

        A *drag* (press and release on different cells) is the user selecting a
        freeform range, which Textual handles at the screen level. We must not
        clobber that selection here, so we detect it via the press offset and
        bail out, only resetting the semantic ladder so the next v/click starts
        small. This mirrors Textual's own click/drag test
        (`screen.py`: `_mouse_down_offset == event.screen_offset`).
        """
        if (
            self._mouse_down_offset is None
            or event.screen_offset != self._mouse_down_offset
        ):
            self._reset_selection_state()
            return
        leaf = find_leaf_block(event.widget)
        if leaf is None:
            return
        if self._sel_scopes is not None and leaf is self._sel_anchor:
            self._sel_index = min(self._sel_index + 1, len(self._sel_scopes) - 1)
        else:
            self._start_selection(leaf)
        self._apply_scope(self._sel_scopes[self._sel_index])
```

- [ ] **Step 6: テストを実行してパスを確認する**

Run: `uv run pytest tests/test_app.py::test_drag_selection_is_not_overwritten_by_click tests/test_app.py::test_stationary_click_still_selects_block -v`

Expected: 両方とも PASS。

- [ ] **Step 7: 全テストを実行して回帰がないことを確認する**

Run: `uv run pytest`

Expected: 全テスト PASS(既存の選択・検索・ナビゲーション系を含む)。

- [ ] **Step 8: コミットする**

```bash
git add src/mdview/app.py tests/test_app.py
git commit -m "$(cat <<'EOF'
Enable mouse-drag text selection

on_click applied a whole-block semantic selection on every click, and a
drag inside one widget still fires a trailing Click, so freeform drag
selections were immediately overwritten. Record the mouse-down offset and
skip the semantic selection when press and release differ, letting the
framework's drag selection stand. Stationary clicks keep selecting blocks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 手動での動作確認(任意)

**Files:** なし(実機確認)

- [ ] **Step 1: 実際にドラッグして確認する**

Run: `uv run mdview README.md`

確認:
- 段落内の語句をマウスでドラッグ → その範囲だけがハイライトされる(ブロック全体に広がらない)。
- 単発クリック → 従来どおりブロック全体が選択され、再クリックで範囲が拡大する。
- `Esc` で選択が解除される。
- ドラッグで範囲選択 → `h`(Ask AI)を押すと、その選択範囲がコンテキストに入る。

---

## Self-Review

- **Spec coverage:** 設計書の「目標(ドラッグ選択の有効化/既存挙動の維持)」「アプローチ A(`on_mouse_down` 記録 + `on_click` ガード + 梯子リセット)」「テスト(ドラッグ非上書き/クリック維持/回帰)」を Task 1 が網羅。非目標(ダブルクリック単語選択など)は実装しない。
- **Placeholder scan:** TBD/TODO 無し。全ステップに実コード/実コマンド/期待結果を記載済み。
- **Type/シンボル整合:** 追加フィールド `_mouse_down_offset`(`Offset | None`)は `on_mouse_down` で代入、`on_click` で参照、いずれも同名。既存の `_reset_selection_state` / `_start_selection` / `_apply_scope` / `find_leaf_block` は現行シグネチャのまま利用。`Offset` は `textual.geometry` から、`Click`/`MouseDown` は `textual.events`(app.py は既存の `from textual import events` 経由で `events.Click` / `events.MouseDown`)から。
