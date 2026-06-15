# Clipboard Copy & File-Tree Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `y` key that copies the current selection to the clipboard, and a file-tree sidebar (`e` to toggle, `mdview <dir>` to launch) that browses Markdown/diff files in a directory.

**Architecture:** Reuse the existing selection basis (`screen.get_selected_text()`) for copy via Textual's OSC52 `copy_to_clipboard`. Add a pure `filetree.py` module (`is_viewable`, `initial_file`) plus a thin `DirectoryTree` subclass, wrap the viewer in a `Horizontal` with the tree on the left, and make `_load_file` diff-aware so diff files render delta-style from the tree.

**Tech Stack:** Python 3.11+, Textual (`DirectoryTree`, `Horizontal`), pytest with `app.run_test()` async pilots, `uv`.

---

## File Structure

- `src/mdview/filetree.py` — **new**, pure/framework-free: `is_viewable(path)` and `initial_file(root)`. Unit-tested directly.
- `src/mdview/app.py` — modify: `action_copy_selection`, `_MdTree` widget, `compose` wrap, `action_toggle_sidebar`, `FileSelected` handler, diff-aware `_load_file`, `__init__(root_dir=...)`, `BINDINGS`.
- `src/mdview/cli.py` — modify: accept a directory argument.
- `src/mdview/theme.css` — modify: sidebar styling.
- `src/mdview/help.py` — modify: document `y` and `e`.
- `tests/test_filetree.py` — **new**, unit tests for the pure module.
- `tests/test_app.py` — modify/add: pilot tests for copy, sidebar, diff-from-tree.

---

## Task 1: Clipboard copy (`y`)

**Files:**
- Modify: `src/mdview/app.py` (BINDINGS near line 192, new action near `action_ask_ai` line 925)
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py` (follow the existing `asyncio.run(...)` + `app.run_test()` pattern in that file; use a small fixture file or an existing one such as `tests/fixtures/`). Adjust the fixture path to match what other tests in the file use.

```python
def test_y_copies_selection_to_clipboard():
    async def scenario():
        app = MdViewerApp(Path("tests/fixtures/simple.md"))
        async with app.run_test() as pilot:
            # Select the whole first block via the v ladder.
            await pilot.press("v")
            await pilot.press("y")
            assert app.clipboard  # non-empty
            assert app.clipboard.strip() != ""
    asyncio.run(scenario())


def test_y_without_selection_notifies_and_keeps_clipboard_empty():
    async def scenario():
        app = MdViewerApp(Path("tests/fixtures/simple.md"))
        async with app.run_test() as pilot:
            await pilot.press("y")
            assert app.clipboard == ""
    asyncio.run(scenario())
```

If `tests/fixtures/simple.md` does not exist, create it with a heading and a paragraph:

```markdown
# Title

Hello world paragraph.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_y_copies_selection_to_clipboard -v`
Expected: FAIL (no `y` binding / `action_copy_selection` missing → key does nothing, clipboard empty).

- [ ] **Step 3: Add the binding and action**

In `src/mdview/app.py` BINDINGS list, after the `w` edit binding (line ~192) add:

```python
        Binding("y", "copy_selection", "Copy", show=True),
```

Add the action method (place near `action_ask_ai`, ~line 925):

```python
    def action_copy_selection(self) -> None:
        selection = self.screen.get_selected_text()
        if not selection or not selection.strip():
            self.notify("選択範囲がありません", severity="warning")
            return
        self.copy_to_clipboard(selection)
        self.notify(f"{len(selection)} 文字をコピーしました")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py::test_y_copies_selection_to_clipboard tests/test_app.py::test_y_without_selection_notifies_and_keeps_clipboard_empty -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add src/mdview/app.py tests/test_app.py tests/fixtures/simple.md
git commit -m "feat: copy selection to clipboard with y"
```

---

## Task 2: Pure file-tree helpers (`filetree.py`)

**Files:**
- Create: `src/mdview/filetree.py`
- Test: `tests/test_filetree.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_filetree.py`:

```python
from pathlib import Path

from mdview.filetree import VIEWABLE_SUFFIXES, initial_file, is_viewable


def test_is_viewable_accepts_markdown_and_diff():
    assert is_viewable(Path("a.md"))
    assert is_viewable(Path("a.markdown"))
    assert is_viewable(Path("a.diff"))
    assert is_viewable(Path("a.patch"))


def test_is_viewable_is_case_insensitive():
    assert is_viewable(Path("README.MD"))


def test_is_viewable_rejects_other_files():
    assert not is_viewable(Path("a.txt"))
    assert not is_viewable(Path("a.py"))


def test_initial_file_prefers_readme(tmp_path):
    (tmp_path / "alpha.md").write_text("a")
    (tmp_path / "README.md").write_text("r")
    assert initial_file(tmp_path) == tmp_path / "README.md"


def test_initial_file_falls_back_to_first_sorted_markdown(tmp_path):
    (tmp_path / "beta.md").write_text("b")
    (tmp_path / "alpha.md").write_text("a")
    assert initial_file(tmp_path) == tmp_path / "alpha.md"


def test_initial_file_none_when_no_markdown(tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    assert initial_file(tmp_path) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_filetree.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mdview.filetree'`.

- [ ] **Step 3: Create the module**

Create `src/mdview/filetree.py`:

```python
"""Pure helpers for the file-tree sidebar: which files are viewable, and which
file to open first when launched on a directory. Framework-free so it can be
unit-tested without a TUI (the Textual wrapper lives in app.py)."""

from __future__ import annotations

from pathlib import Path

# Extensions the viewer can render: Markdown and unified diffs.
VIEWABLE_SUFFIXES = frozenset({".md", ".markdown", ".diff", ".patch"})


def is_viewable(path: Path) -> bool:
    """True if *path* is a file type the viewer renders (case-insensitive)."""
    return path.suffix.lower() in VIEWABLE_SUFFIXES


def initial_file(root: Path) -> Path | None:
    """Pick the file to open when launched on directory *root*: a top-level
    README.md if present, else the first viewable file in sorted order, else
    None (empty directory → caller shows a placeholder)."""
    try:
        entries = sorted(p for p in root.iterdir() if p.is_file() and is_viewable(p))
    except OSError:
        return None
    for entry in entries:
        if entry.name.lower() == "readme.md":
            return entry
    return entries[0] if entries else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_filetree.py -v`
Expected: PASS (all 6).

- [ ] **Step 5: Commit**

```bash
git add src/mdview/filetree.py tests/test_filetree.py
git commit -m "feat: add pure file-tree helpers (is_viewable, initial_file)"
```

---

## Task 3: Diff-aware `_load_file`

**Files:**
- Modify: `src/mdview/app.py` (`_load_file`, ~line 834)
- Test: `tests/test_app.py`

This makes opening a `.diff`/`.patch` (from the tree in Task 5, or a link) render delta-style. Currently `_load_file` always renders Markdown.

- [ ] **Step 1: Write the failing test**

Create a diff fixture `tests/fixtures/sample.diff`:

```diff
--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,2 @@
-old line
+new line
 unchanged
```

Add to `tests/test_app.py`:

```python
from mdview.diff_widget import DiffHunk


def test_load_file_renders_diff_as_hunks():
    async def scenario():
        app = MdViewerApp(Path("tests/fixtures/simple.md"))
        async with app.run_test() as pilot:
            await app._load_file(Path("tests/fixtures/sample.diff"))
            await pilot.pause()
            assert app.query(DiffHunk)
            assert app._diff_files is not None
    asyncio.run(scenario())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_load_file_renders_diff_as_hunks -v`
Expected: FAIL (no `DiffHunk` injected — diff rendered as a raw code block, `_diff_files` stays None).

- [ ] **Step 3: Make `_load_file` diff-aware**

In `src/mdview/app.py`, edit `_load_file` (~line 834). After `text = path.read_text(...)` succeeds and before `await self._render_source(text)`, branch on diff detection:

```python
    async def _load_file(self, path: Path, anchor: str = "") -> bool:
        viewer = self.query_one(MarkdownViewer)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            self.notify(f"failed to load {path}: {e}", severity="error")
            return False
        self._md_path = path
        self._md_dir = path.parent
        self.title = path.name
        # A .diff/.patch (or content that looks like a unified diff) renders
        # delta-style: parse it, set the diff model, and feed the scaffolded
        # Markdown to the renderer. Anything else is plain Markdown.
        from mdview.diff import diff_to_markdown, looks_like_diff, parse_diff

        if looks_like_diff(text):
            self._diff_files = parse_diff(text)
            await self._render_source(diff_to_markdown(self._diff_files))
        else:
            self._diff_files = None
            await self._render_source(text)
        # Navigating to a new document starts a fresh edit session.
        self._disk_baseline = text
        self._undo_stack.clear()
        self._editing = False
        self._start_watching()  # re-point the watcher at the new directory/file
        if anchor:
            self.call_after_refresh(viewer.document.goto_anchor, anchor)
        else:
            viewer.scroll_home(animate=False)
        return True
```

Note: `_inject_diff_hunks` reads `self._diff_files`, so setting it before `_render_source` is required.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py::test_load_file_renders_diff_as_hunks -v`
Expected: PASS.

Also run the full app suite to ensure markdown navigation still works:
Run: `uv run pytest tests/test_app.py -v`
Expected: PASS (no regressions).

- [ ] **Step 5: Commit**

```bash
git add src/mdview/app.py tests/test_app.py tests/fixtures/sample.diff
git commit -m "feat: render diff files delta-style when loaded via _load_file"
```

---

## Task 4: `_MdTree` widget + sidebar in compose (toggle with `e`)

**Files:**
- Modify: `src/mdview/app.py` (imports, `_MdTree` class, `__init__`, `compose`, `BINDINGS`, new action)
- Modify: `src/mdview/theme.css`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
from textual.widgets import DirectoryTree


def test_e_toggles_sidebar_visibility():
    async def scenario():
        app = MdViewerApp(Path("tests/fixtures/simple.md"))
        async with app.run_test() as pilot:
            sidebar = app.query_one("#sidebar", DirectoryTree)
            # Single-file launch: sidebar starts hidden.
            assert not sidebar.display
            await pilot.press("e")
            assert sidebar.display
            assert app.focused is sidebar
            await pilot.press("e")
            assert not sidebar.display
    asyncio.run(scenario())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_e_toggles_sidebar_visibility -v`
Expected: FAIL (`#sidebar` not found / no `e` binding).

- [ ] **Step 3: Add the widget, compose wrap, init, binding, action**

In `src/mdview/app.py`:

(a) Imports near the other Textual imports:

```python
from textual.containers import Horizontal
from textual.widgets import DirectoryTree
```

(`Horizontal` may already be imported — if so, don't duplicate.)

(b) Import the pure helper near the other `from mdview...` imports:

```python
from mdview.filetree import initial_file, is_viewable
```

(c) Add the `_MdTree` class above `MdViewerApp` (near `_MdViewer`, ~line 111):

```python
class _MdTree(DirectoryTree):
    """DirectoryTree filtered to viewable files (Markdown/diff) and dirs."""

    def filter_paths(self, paths):
        return [p for p in paths if p.is_dir() or is_viewable(p)]
```

(d) In `MdViewerApp.__init__`, add the `root_dir` parameter and stash it:

```python
    def __init__(
        self,
        md_path: Path | None = None,
        *,
        content: str | None = None,
        base_dir: Path | None = None,
        diff_files: list[FileDiff] | None = None,
        root_dir: Path | None = None,
    ) -> None:
        super().__init__()
        # Directory the file-tree sidebar is rooted at. When given on launch
        # (`mdview <dir>`) the sidebar starts visible; otherwise it defaults to
        # the viewed file's parent and starts hidden (toggle with `e`).
        self._root_dir = root_dir.resolve() if root_dir is not None else None
        ...
```

(Keep the rest of `__init__` unchanged.)

(e) Change `compose` to wrap the viewer in a `Horizontal` with the tree. The
sidebar root is `root_dir` if launched on a directory, else the file's dir (or
CWD for stdin). Replace the existing `yield _MdViewer(...)` line:

```python
    def compose(self) -> ComposeResult:
        tree_root = self._root_dir or self._md_dir
        with Horizontal(id="main-row"):
            tree = _MdTree(str(tree_root), id="sidebar")
            tree.display = self._root_dir is not None
            yield tree
            # open_links=False so we route anchors (#section) to goto_anchor
            # ourselves instead of letting Textual hand them to the OS browser.
            yield _MdViewer(show_table_of_contents=False, open_links=False)
        with Horizontal(id="cmdline-bar"):
            yield Static("", id="cmdline-prompt")
            yield _CommandLine(placeholder="検索 / コマンド", id="cmdline")
            yield Static("", id="cmdline-count")
```

(f) Add the binding after the `y` binding:

```python
        Binding("e", "toggle_sidebar", "Files", show=True),
```

(g) Add the action (near `action_open_toc`):

```python
    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar", _MdTree)
        sidebar.display = not sidebar.display
        if sidebar.display:
            sidebar.focus()
        else:
            self.set_focus(None)
```

- [ ] **Step 4: Add sidebar CSS**

In `src/mdview/theme.css`, after the `MarkdownViewer` block (~line 15) add:

```css
#main-row {
    height: 1fr;
}

#sidebar {
    width: 32;
    border-right: solid $orange 30%;
    background: $surface;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py::test_e_toggles_sidebar_visibility -v`
Expected: PASS.

Run: `uv run pytest tests/test_app.py -v`
Expected: PASS (no regressions — `query_one(MarkdownViewer)` still resolves uniquely).

- [ ] **Step 6: Commit**

```bash
git add src/mdview/app.py src/mdview/theme.css tests/test_app.py
git commit -m "feat: add file-tree sidebar toggled with e"
```

---

## Task 5: Open files from the tree (`FileSelected`)

**Files:**
- Modify: `src/mdview/app.py` (new message handler)
- Test: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
def test_selecting_tree_file_switches_viewer():
    async def scenario():
        # Launch on the fixtures directory so the tree is rooted there.
        app = MdViewerApp(
            Path("tests/fixtures/simple.md"),
            root_dir=Path("tests/fixtures"),
        )
        async with app.run_test() as pilot:
            target = Path("tests/fixtures/sample.diff").resolve()
            app.on_directory_tree_file_selected(
                DirectoryTree.FileSelected(
                    app.query_one("#sidebar", DirectoryTree).root, target
                )
            )
            await pilot.pause()
            await pilot.pause()
            assert app._md_path == target
    asyncio.run(scenario())
```

Note: if constructing the `FileSelected` message directly is awkward (its
signature is internal), instead drive it through the tree by expanding the root
and pressing Enter on a node; pick whichever the Textual version in this repo
supports. The behavioral assertion (`app._md_path == target`) is what matters.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_selecting_tree_file_switches_viewer -v`
Expected: FAIL (no handler → `_md_path` unchanged).

- [ ] **Step 3: Add the handler**

In `src/mdview/app.py`, add a message handler on `MdViewerApp`:

```python
    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        # Route tree selections through the same history-tracking navigation as
        # link clicks, then return focus to the viewer so reading keys work.
        event.stop()
        path = Path(event.path)
        if path.resolve() == self._md_path:
            self.set_focus(None)
            return
        self.run_worker(self._navigate_to(path, ""), exclusive=True)
        self.set_focus(None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py::test_selecting_tree_file_switches_viewer -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mdview/app.py tests/test_app.py
git commit -m "feat: open the selected tree file in the viewer"
```

---

## Task 6: Directory launch in `cli.py`

**Files:**
- Modify: `src/mdview/cli.py`
- Test: `tests/test_app.py` (or a new `tests/test_cli.py` if the repo has one — check first; `tests/` currently has no `test_cli.py`, so add a focused pilot test in `tests/test_app.py`)

- [ ] **Step 1: Write the failing test**

The launch wiring (`main`) calls `.run()`, which is hard to unit-test directly.
Test the observable construction instead: that an app built with `root_dir`
shows the sidebar and opens the README. Add to `tests/test_app.py`:

```python
def test_directory_launch_shows_sidebar_and_opens_readme(tmp_path):
    async def scenario():
        (tmp_path / "README.md").write_text("# Readme\n\nbody\n")
        (tmp_path / "other.md").write_text("# Other\n")
        from mdview.filetree import initial_file

        first = initial_file(tmp_path)
        app = MdViewerApp(first, root_dir=tmp_path)
        async with app.run_test() as pilot:
            sidebar = app.query_one("#sidebar", DirectoryTree)
            assert sidebar.display  # visible on directory launch
            assert app._md_path == (tmp_path / "README.md").resolve()
    asyncio.run(scenario())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_directory_launch_shows_sidebar_and_opens_readme -v`
Expected: PASS already for the app layer if Task 4 is done (the sidebar shows and README opens). If it passes, that confirms the app contract; the cli wiring below is still needed for the real entry point. If you want a guaranteed red first, write this test BEFORE Task 4. Otherwise proceed to wire `cli.py`.

- [ ] **Step 3: Handle a directory argument in `cli.py`**

In `src/mdview/cli.py`, replace the `is_file()` guard (lines ~29-31) and the
launch block so a directory is accepted. After the `path.exists()` check:

```python
    if not path.exists():
        print(f"mdview: {path}: no such file", file=sys.stderr)
        sys.exit(1)

    if path.is_dir():
        if not sys.stdout.isatty():
            print(f"mdview: {path}: is a directory", file=sys.stderr)
            sys.exit(1)
        from mdview.app import MdViewerApp
        from mdview.filetree import initial_file

        first = initial_file(path)
        MdViewerApp(first, root_dir=path).run()
        return

    if not path.is_file():
        print(f"mdview: {path}: not a regular file", file=sys.stderr)
        sys.exit(1)
```

(The rest of `main` — diff detection and single-file launch — stays unchanged.)

Note: `MdViewerApp(None, root_dir=path)` is valid when the directory has no
viewable file (`first` is None). Verify the app tolerates `md_path=None` with a
`root_dir`: in `on_mount`, `self._md_path` would be None. Guard `on_mount` so an
empty directory shows a placeholder instead of crashing — see Step 4.

- [ ] **Step 4: Guard `on_mount` / `__init__` for an empty directory**

In `src/mdview/app.py` `__init__`, the `else` branch currently does
`self._md_path = md_path.resolve()`. Handle `md_path is None` (directory launch
with no viewable file):

```python
        else:
            if md_path is None:
                # Directory launch with no viewable file: no document yet.
                self._md_path = None
                self._md_dir = (self._root_dir or Path.cwd())
                self._display_name = "(no file)"
            else:
                self._md_path = md_path.resolve()
                self._md_dir = self._md_path.parent
                self._display_name = self._md_path.name
```

In `on_mount` (~line 305), guard the read:

```python
    async def on_mount(self) -> None:
        self.title = self._display_name
        if self._md_path is None:
            self.notify("左のツリーからファイルを選択してください")
            self.query_one("#sidebar", _MdTree).focus()
            return
        try:
            text = self._md_path.read_text(encoding="utf-8")
        except OSError as e:
            self.exit(message=f"mdview: failed to load {self._md_path}: {e}")
            return
        await self._render_source(text)
        self._disk_baseline = text
        self._start_watching()
```

Also confirm `self._md_path: Path | None` is consistent — update the type
annotation where it's first set if one exists. `_start_watching` is only called
when a file is loaded, so the None case never watches.

- [ ] **Step 5: Write the empty-directory test**

Add to `tests/test_app.py`:

```python
def test_empty_directory_launch_shows_placeholder(tmp_path):
    async def scenario():
        (tmp_path / "notes.txt").write_text("not markdown")
        from mdview.filetree import initial_file

        app = MdViewerApp(initial_file(tmp_path), root_dir=tmp_path)
        async with app.run_test() as pilot:
            assert app._md_path is None
            assert app.query_one("#sidebar", DirectoryTree).display
    asyncio.run(scenario())
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_app.py::test_directory_launch_shows_sidebar_and_opens_readme tests/test_app.py::test_empty_directory_launch_shows_placeholder -v`
Expected: PASS (both).

- [ ] **Step 7: Commit**

```bash
git add src/mdview/cli.py src/mdview/app.py tests/test_app.py
git commit -m "feat: launch on a directory with the file-tree sidebar"
```

---

## Task 7: Document `y` and `e` in help

**Files:**
- Modify: `src/mdview/help.py` (`HELP_SECTIONS`, ~line 25)
- Modify: `README.md` (feature list)

- [ ] **Step 1: Add to HELP_SECTIONS**

In `src/mdview/help.py`, add entries to the appropriate groups. In the selection/AI group add `("y", "選択範囲をコピー")`; add a navigation/files entry `("e", "ファイルツリー サイドバー 開閉")`. Match the exact tuple format of the surrounding entries.

- [ ] **Step 2: Add to README.md**

In `README.md`'s 特徴 list, add two bullets:

```markdown
- **クリップボードへコピー** — 本文を選択して `y` でシステムクリップボードへコピー（OSC52、SSH 越しも対応）。
- **ファイルツリー** — `mdview <dir>` でディレクトリを開く、または `e` でサイドバーを開閉して `.md`/`.diff` を切り替え閲覧。
```

- [ ] **Step 3: Verify help renders (smoke test)**

Run: `uv run pytest tests/ -k help -v` (if a help test exists) or visually confirm later.
Expected: PASS / no error.

- [ ] **Step 4: Commit**

```bash
git add src/mdview/help.py README.md
git commit -m "docs: document y (copy) and e (file tree) keybindings"
```

---

## Task 8: Full suite + CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md` (Architecture, Keybindings, Notable modules)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`
Expected: PASS (all tests, including the new ones).

- [ ] **Step 2: Update CLAUDE.md**

Add to CLAUDE.md:
- Keybindings paragraph: `y` copies the selection (OSC52 via `copy_to_clipboard`); `e` toggles the file-tree sidebar.
- A note that `mdview <dir>` launches with the sidebar, `filetree.py` is the new pure module (`is_viewable`/`initial_file`) with `_MdTree` as its thin `DirectoryTree` wrapper, and that `_load_file` is now diff-aware (sets `_diff_files` from `looks_like_diff`).
- Note `_md_path` can be `None` on an empty-directory launch.

Keep the prose style of the existing CLAUDE.md (explain *why*).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for clipboard copy and file tree"
```

---

## Self-Review Notes

- **Spec coverage:** copy (Task 1), `is_viewable`/`initial_file` (Task 2), diff-aware load (Task 3), sidebar+`e`+layout (Task 4), tree open via `_navigate_to` (Task 5), directory launch + non-TTY error + empty-dir placeholder (Task 6), help/README (Task 7), CLAUDE.md (Task 8). All spec sections mapped.
- **Type consistency:** `is_viewable(path: Path) -> bool`, `initial_file(root: Path) -> Path | None`, `_MdTree`, `#sidebar`, `root_dir`, `_root_dir`, `_diff_files`, `action_copy_selection`, `action_toggle_sidebar` used consistently across tasks.
- **Known caution:** Task 5's direct `FileSelected` construction may vary by Textual version — the task notes the fallback (drive via Enter on a node) and that the behavioral assertion is the contract. Task 6 Step 2 explains the test may pass at the app layer before cli wiring; ordering note included.
