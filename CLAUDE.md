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
- **Diff detection**: `.diff`/`.patch` files and piped input that `looks_like_diff` are rewritten by `diff.py` into structured Markdown *before* rendering — for both the TUI and non-TTY paths.

### The TUI (`app.py:MdViewerApp`)
Wraps Textual's `MarkdownViewer`. The core pattern: load the document, then **post-process the rendered widget tree** in `on_mount` / `_load_file`:
- `_inject_images` — swaps image-only paragraphs for `Image` / `ZoomableImage` widgets.
- `_inject_mermaid` — swaps ```mermaid fences for rendered PNGs (only if `mmdc` is on PATH).
- `_recolor_diff_fences` — restyles ```diff fences with `_DiffHighlightTheme` (Textual leaves +/- lines uncoloured).

**Key design rule: all relative paths (images, links) resolve against the *viewed document's* directory, not the process CWD.** This is why `_MdViewer` overrides `_on_markdown_link_clicked` to suppress the base class's CWD-based navigator — the app routes link clicks itself (`on_markdown_link_clicked` → `_navigate_to`), keeps a `_history` stack for `b`/back, and handles `#anchor` links.

### Isolation pattern (testability)
Anything touching a subprocess or rasterization is split into a **pure module** (unit-testable without a TUI) plus a thin Textual wrapper:
- `ai.py` (subprocess + prompt building) ↔ `ask_ai.py` (`AskAiScreen` modal)
- `svg.py`, `mermaid.py`, `diff.py`, `selection.py` are all pure / framework-free.

When adding rendering or subprocess logic, keep the pure part in its own module and unit-test it directly.

### Notable modules
- **`diff.py`** — purely deterministic string transform (no LLM): each file → `##` heading, each `@@` hunk → `### @@…` heading + ```diff fence. `looks_like_diff` is front-anchored so ordinary Markdown that merely *embeds* a diff isn't misclassified.
- **`selection.py`** — semantic-selection "expansion ladder" (block → list item → list/quote → section → document). Pure functions over the Textual widget tree; `app.py` applies the scopes. Note the tree quirks documented at the top: list items are `Horizontal` under `MarkdownList` (no `MarkdownListItem` widget is mounted), and tables are atomic.
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
