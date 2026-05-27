# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`mdview` is a TUI Markdown viewer built on [Textual](https://textual.textualize.io/). It renders images, SVGs, and Mermaid diagrams inline, colourizes diffs, and can ask the `claude` CLI about selected text. Entry point is `mdview.cli:main`. Python 3.11+, managed with `uv`.

## Commands

```sh
uv sync                                   # install deps (incl. dev group)
uv run pytest                             # run all tests
uv run pytest tests/test_diff.py          # one test file
uv run pytest tests/test_app.py::test_all_headings_render_in_claude_orange  # one test
uv run mdview README.md                   # run without installing
uv tool install --editable .              # install as a global `mdview` (editable)
uv tool install --force --reinstall .     # rebuild + reinstall to pick up changes
```

There is no linter or formatter configured; match the surrounding style (`from __future__ import annotations`, type hints, module docstrings explaining *why*).

## Architecture

### Entry and output routing (`cli.py`)
`main` decides the rendering path before anything renders:
- **Non-TTY stdout** (pipe/CI/`| less`) → `render.py` prints with Rich, no TUI.
- **TTY** → launches `app.MdViewerApp` (Textual).
- **stdin** (`mdview -`): after reading the pipe, fd 0 is re-pointed at `/dev/tty` so the TUI can still read keys.
- **Diff detection**: `.diff`/`.patch` files and piped input that `looks_like_diff` are parsed by `diff.py` into a model (`list[FileDiff]`). The TUI renders it as `## file` Markdown headings + per-hunk ```diff fences (swapped for delta widgets, see below); the non-TTY path renders the model directly with Rich (`render.print_diff`).

### The TUI (`app.py:MdViewerApp`)
Wraps Textual's `MarkdownViewer`. The core pattern: load the document, then **post-process the rendered widget tree** in `on_mount` / `_load_file`:
- `_inject_images` — swaps image-only paragraphs for `Image` / `ZoomableImage` widgets.
- `_inject_mermaid` — swaps ```mermaid fences for rendered PNGs (only if `mmdc` is on PATH).
- `_inject_diff_hunks` — swaps each ```diff fence for a delta-styled `DiffHunk` widget (line-number gutter, green/red background bars, per-language syntax highlighting). `## @ file` headings stay (so the TOC lists changed files and `]`/`[` jump between them); `@@` hunk headers are *not* headings — `}`/`{` jump between hunks instead.
- `_inject_section_insights` — adds a clickable 💡 to the right of each `##` heading (skipped if `claude` is absent or for a whole-document diff). Clicking it (`action_section_insight`, routed via a Content `@click` action) runs `claude` on that section's Markdown (`selection.py:section_source` — from the `##` down to the next equal-or-higher heading) plus the whole document as context, with SVG always on (and `concise_svg=True` + a longer `_INSIGHT_TIMEOUT_S` (240s) so an illustrated answer fits in time — Ask AI keeps the 120s / full-detail defaults); while running the 💡 spins (a `set_interval` timer over `_INSIGHT_SPINNER`), and on success it becomes 📦 whose click opens `section_insight.py:SectionInsightScreen` (the diagram(s) above the prose). Up to `_INSIGHT_MAX_CONCURRENT` (3) generate at once — counted synchronously in the action so the cap is exact — a 4th click is refused with a notice. **The heading widget is left structurally untouched** (so TOC/`query(MarkdownHeader)`/`selection.py`'s `document.children` section logic all keep working) — only its rendered `_content` gains the marker, via `set_content(base + marker)` where the clean pre-marker `Content` is stashed on `heading._insight_base`. A per-instance `get_selection` override (`_insight_get_selection`) and the `_insight_base` branch in `_search_text` keep the marker out of copied/AI'd/searched text; the TOC is built from clean content at load time so it's unaffected. `_load_file` calls `_reset_insights` so a navigated-away document drops its markers (in-flight workers guard on `hid in _insight_headings` and drop their result).

**Keybindings (less/delta-style, see `BINDINGS`):** quit is `q` or `:q`; **`Esc` never quits** — it cancels the current transient state (`action_cancel`: stop editing the command line, clear an active search, and drop the current selection — resetting the `v`/click ladder so the next selection starts small) and is a no-op when idle. `/` and `:` open one **unified command line** (`_CommandLine` in the docked `#cmdline-bar`): the leading `/`/`:` is *editable text* (less/vim-style), so Backspace deletes it and you retype the other prefix to switch modes. `on_input_submitted` → `_run_cmdline` dispatches on that first char: `:` → `command.py:parse_command` (`:q`/`:quit` quit, `:h`/`:help` open help), anything else → search (a leading `/` is stripped). Scrolling follows less: `j`/`k` lines, `d`/`u` half-page, `f`/`b` full page (so **`b` is page-up, not back** — link-history back moved to `Backspace`/`←`), `g`/`G` top/bottom. Search match nav is `n`/`N`. Structural nav: **`Space`/`Shift+Space`** are the ergonomic context-aware pair (`action_next_section`/`prev_section` → headings in prose, headings + `@@` hunks in a diff, via `_section_targets`); `]`/`[` (headings, = files in a diff) and `}`/`{` (diff hunks) are the explicit always-available keys, and `[`/`{` are the reliable "previous" since many terminals can't distinguish `Shift+Space` from `Space`. `Ctrl+]`/`Ctrl+[` narrow to level-2 (`##`) headings only (`action_next_h2`/`prev_h2` → `_headings_at_level(2)`, filtering on each `MarkdownH*`'s `LEVEL`). Note `Ctrl+[` is the ESC byte in legacy terminals (so it triggers `cancel`, not prev-H2, unless the kitty keyboard protocol is active); `[` stays the reliable all-heading prev. `h` is Ask AI; `?` or `:h` open the help screen (`help.py:HelpScreen`, a custom grouped cheat-sheet — the viewer has no permanent footer). Punctuation bindings use Textual key *names* (`]`=`right_square_bracket`, `}`=`right_curly_bracket`, `:`=`colon`).

**Navigation/search:** `/` opens the unified command line (`_CommandLine`, `#cmdline`) in search mode — the field reads like less, a leading `/` then the pattern; the query (text after the `/`) is a case-insensitive regex (invalid → literal, see `search.py`). On submit, `_run_search` scans every atomic block's `_search_text` and records one **hit per matched substring** (`_search_hits` = `(block, start, end)`); `n`/`N` step through hits **one occurrence at a time** (`_search_index`), so a block with several matches is walked occurrence-by-occurrence rather than skipped in one jump (empty query clears the search, after which `n`/`N` are no-ops; headings stay on `]`/`[` and hunks on `}`/`{`). Each hit stores the match's line index within its block, so `_focus_current` scrolls to the matched *line* (`block.virtual_region.y + line`), not just the block top — stepping through hits inside one tall fence/hunk still moves the view. The bar stays up as a status line (query + `i/N` position). Highlighting is **per-word**: `_paint_widget` washes just the matched substrings (`Content.highlight_regex` for Markdown blocks/fences; Rich `Text.highlight_regex` on a re-rendered `render_hunk` for `DiffHunk`), subtle green for the set and brighter+bold (`stylize` over the current span) for the current hit. **`_search_text` must be the exact text the colours land on** — for `DiffHunk` that's the *rendered* text (gutter included), not `_plain`, so finditer offsets map to what's drawn. `_restore_block`/`_search_originals` undo it; `_search_matches` is the de-duped hit blocks (for restore); `.search-current` is a no-style marker class on the current block (for tests). `_load_file` calls `_end_search` so an active search doesn't carry stale widget refs into a newly-navigated document. (Known limitation: table cell text isn't searchable — see `_search_text`.) The diff file-heading `@ ` prefix is the hook that makes this work for diffs: a heading's text starts with `@ ` and a hunk header with `@@ `, so `^@ ` filters to files and `@@` to hunks. (The viewer is `can_focus=False`, so on submit the app blurs the input with `set_focus(None)` rather than focusing the viewer, letting `n`/`N` reach the App bindings.)

**Key design rule: all relative paths (images, links) resolve against the *viewed document's* directory, not the process CWD.** This is why `_MdViewer` overrides `_on_markdown_link_clicked` to suppress the base class's CWD-based navigator — the app routes link clicks itself (`on_markdown_link_clicked` → `_navigate_to`), keeps a `_history` stack for `Backspace`/back, and handles `#anchor` links.

### Isolation pattern (testability)
Anything touching a subprocess or rasterization is split into a **pure module** (unit-testable without a TUI) plus a thin Textual wrapper:
- `ai.py` (subprocess + prompt building) ↔ `ask_ai.py` (`AskAiScreen` modal; its context line is a clickable `_SelectionContext` that opens `SelectionViewScreen` — a nested `ScrollableModalScreen` showing the *full* selection, since the context only previews it truncated. A diff selection (`diffview.is_diff_text`) gets the delta look via `diffview.render_selection`; everything else is re-rendered with a bare `Markdown` widget so it inherits the main view's colours **and line spacing** — theme.css styles `Markdown`/`MarkdownBlock` by type, so the popup matches without extra CSS) ↔ `section_insight.py` (`SectionInsightScreen` — the read-only `##`-lightbulb result modal, no question box; reuses the same `Markdown`-prose-+-SVG layout)
- `svg.py` (pure rasterize/`extract_svgs`) ↔ `svg_widgets.py` (the thin Textual wrapper: `svg_to_zoomable_image` / `render_svgs_into` turn SVG markup into mounted `ZoomableImage`s; shared by `ask_ai.py` and `section_insight.py`).
- `mermaid.py`, `diff.py`, `diffview.py`, `selection.py`, `search.py`, `command.py` are all pure / framework-free (`command.py:parse_command` maps `:` input → a canonical command name; `selection.py:section_source` returns a heading's section as clean Markdown sliced from `document.source`).
- `help.py` (`HelpScreen` + a hand-maintained `HELP_SECTIONS` cheat-sheet rendered with Rich) ↔ opened by `?` / `:h`.
- `scroll_modal.py` (`ScrollableModalScreen`) — a `ModalScreen` base that re-binds the movement keys (`j`/`k`, `d`/`u`, `f`/`b`, Space, `g`/`G`) to scroll the modal's own `scroll_region()` instead of the document behind it; `HelpScreen` and `AskAiScreen` subclass it (`TocScreen` does the same for its `Tree` via explicit bindings). **Must be a real `ModalScreen` subclass, not a mixin** — Textual collects `BINDINGS` only from `DOMNode` classes in the MRO. A focused single-line `Input` still swallows the printable letters as text, so inside Ask AI you scroll the answer with the arrows / PageUp / PageDown while the question box is focused.
- `diffview.py` (delta-style hunk → Rich `Text`) ↔ `diff_widget.py` (`DiffHunk`, a `Static` whose `render` is that `Text`; `get_selection` returns the clean unified diff so a selected/copied hunk stays valid for Ask AI).

When adding rendering or subprocess logic, keep the pure part in its own module and unit-test it directly.

### Notable modules
- **`diff.py`** — purely deterministic (no LLM). `parse_diff` builds a `list[FileDiff]` model (files → hunks → classified, line-numbered `DiffLine`s; `hunk.raw` is the clean unified-diff text). `diff_to_markdown(files)` scaffolds the TUI document (`## @ file` heading — the `@ ` is the `/` search hook, see app.py — + one ```diff placeholder fence per hunk — **no** `### @@` headings). `parse_hunk_lines` parses a standalone fence body (a diff example authored inside ordinary Markdown). `looks_like_diff` is front-anchored so Markdown that merely *embeds* a diff isn't misclassified.
- **`diffview.py`** — renders a parsed `Hunk` to a delta-styled Rich `Text` (`render_hunk`): two-column line-number gutter, `+`/`-` markers kept, green/red full-line background bars (`ADD_BG`/`DEL_BG`), code syntax-highlighted in the file's language (`guess_lexer` + Rich `Syntax`). Shared by the TUI widget and `render.print_diff`.
- **`selection.py`** — semantic-selection "expansion ladder" (block → list item → list/quote → section → document). Pure functions over the Textual widget tree; `app.py` applies the scopes. Note the tree quirks documented at the top: list items are `Horizontal` under `MarkdownList` (no `MarkdownListItem` widget is mounted), and tables are atomic.
- **`search.py`** — `compile_query(query)` for the `/` jump feature: a case-insensitive regex, or `None` for empty, or an escaped literal if the query isn't valid regex (so a half-typed pattern never raises). Compiled with the **`regex`** module (a superset of `re`) so the caller can pass `finditer(text, timeout=…)`; `_run_search` gives each block the remaining `_SEARCH_BUDGET_S` and aborts on `TimeoutError`, so a catastrophic-backtracking pattern can't hang the UI thread (stdlib `re` has no timeout and backtracks in C, ignoring signals).
- **`svg.py`** — `rasterize_svg` via cairosvg. Two non-obvious fixes: splices a CJK font stylesheet into the SVG (cairo's toy font API does no per-glyph fallback → Japanese renders as tofu), and augments `DYLD_FALLBACK_LIBRARY_PATH` on macOS so Homebrew's libs load. `extract_svgs` pulls SVG blocks out of AI answers.
- **`mermaid.py`** — renders via `mmdc` to **PNG, not SVG**, because Mermaid's flowchart `<foreignObject>` labels are dropped by cairosvg.
- **`image_zoom.py`** — `ZoomableImage` *wraps* an `Image` (textual_image's `Image` can't be subclassed) to make it click-to-zoom.

### Generated files
All rendered PNGs/SVGs go to a per-run `TemporaryDirectory` (`MdViewerApp._tempdir`), cleaned up by its finalizer. Ask AI in SVG mode tells `claude` to save diagrams into a subdir of that tempdir (`ai-answer-svg/`) rather than into the repo.

### Optional external tools (degrade gracefully when absent)
- `mmdc` (`@mermaid-js/mermaid-cli`) — Mermaid diagrams; without it, fences stay as code blocks.
- `claude` CLI — the Ask AI (`h`) feature; without it, the key shows a notice.

## Testing

Textual app tests drive the UI with `app.run_test()` and an async pilot, wrapped in `asyncio.run` (see `tests/test_app.py`). Pure modules are tested directly. Fixtures live in `tests/fixtures/`.
