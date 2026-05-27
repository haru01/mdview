from __future__ import annotations

import hashlib
import tempfile
import types
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from urllib.parse import unquote

import regex

from markdown_it.token import Token
from rich.cells import cell_len
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.content import Content
from textual.css.query import NoMatches
from textual.geometry import Offset
from textual.selection import SELECT_ALL, Selection
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Input, Label, Markdown, MarkdownViewer, Static
from textual.widgets._markdown import (
    MarkdownBlock,
    MarkdownFence,
    MarkdownHeader,
    MarkdownParagraph,
    MarkdownTableOfContents,
)
from textual_image.widget import Image

from mdview.ai import AiQueryError, ask_claude, find_claude
from mdview.ask_ai import AskAiScreen
from mdview.command import parse_command
from mdview.diff import FileDiff, parse_hunk_lines
from mdview.diff_widget import DiffHunk
from mdview.diffview import render_hunk
from mdview.eventflow import parse_flow_dsl
from mdview.eventflow_widget import EventFlow
from mdview.help import HelpScreen
from mdview.image_zoom import ZoomableImage
from mdview.mermaid import MermaidRenderError, find_mmdc, render_mermaid
from mdview.search import compile_query
from mdview.section_insight import SectionInsightScreen
from mdview.selection import ATOMIC_BLOCKS, build_scopes, find_leaf_block, section_source
from mdview.svg import SvgRenderError, extract_svgs, rasterize_svg
from mdview.toc import TocScreen


# Section insight (`##` lightbulb → treasure): the inline marker's three states
# and the fixed prompt. Up to three sections may generate at once; a fourth
# click is refused. The marker lives in the heading's rendered Content (so it
# scrolls with the heading and needs no overlay); a per-heading `get_selection`
# override keeps it out of copied/searched/AI'd text.
_INSIGHT_GLYPHS = {"idle": "💡", "done": "📦", "error": "⚠"}
_INSIGHT_SPINNER = "◐◓◑◒"
_INSIGHT_MAX_CONCURRENT = 3
_INSIGHT_QUESTION = "このセクションの内容を、図解のSVGを交えてわかりやすく解説してください。"
# An SVG-illustrated section explanation can take longer than the Ask AI default,
# so allow more time; `concise_svg` keeps the diagram simple to stay within it.
_INSIGHT_TIMEOUT_S = 240.0


@dataclass
class _InsightState:
    status: str = "idle"  # idle | running | done | error
    prose: str = ""
    svgs: list[str] = field(default_factory=list)


def _insight_get_selection(self: MarkdownHeader, selection: Selection):
    """Instance override for an H2 with a lightbulb: select from the *clean*
    pre-marker content so the 💡/📦 marker never leaks into copied or AI'd text.
    """
    base = getattr(self, "_insight_base", None)
    text = base.plain if base is not None else str(self._render())
    return selection.extract(text), "\n"


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_MARKDOWN_EXTS = {".md", ".markdown", ".mdown", ".mkd"}

# `/` search: colour applied to the matched substrings themselves (per-word, not
# the whole block). The set gets a muted green wash; the current match (where
# n/N landed) a brighter, bold one. These strings parse for both Textual
# `Content.highlight_regex` and Rich `Text.highlight_regex` (the DiffHunk path).
_MATCH_HL = "on #335c46"
_CURRENT_HL = "bold on #4ebf71"

# Wall-clock budget for one search scan. A catastrophic-backtracking pattern
# (e.g. `(a+)+$`) would otherwise hang the UI thread, so each `finditer` is given
# the remaining budget as a `timeout=` and a `TimeoutError` aborts the search.
_SEARCH_BUDGET_S = 1.0


class _MdViewer(MarkdownViewer):
    """MarkdownViewer that routes link clicks through the App.

    The base class loads `[..](other.md)` via its navigator, which resolves
    against the process CWD instead of the current document's directory. We
    suppress that handler so the click bubbles to the App, which resolves paths
    relative to the file being viewed.
    """

    async def _on_markdown_link_clicked(self, message: Markdown.LinkClicked) -> None:
        # prevent_default() suppresses MarkdownViewer's base handler in the
        # same MRO dispatch, so the message still bubbles up to the App.
        message.prevent_default()


class _CommandLine(Input):
    """The unified `/`-search / `:`-command line (less/vim-style).

    The leading `/` or `:` is *part of the editable value*, not a fixed prompt,
    so Backspace deletes it and you can retype the other prefix to switch modes
    mid-edit. The mode is decided from the first character on submit (see
    `app._run_cmdline`). Esc stops editing here — bound on the focused widget so
    it doesn't bubble to the App's `cancel` (which clears the search/selection).
    """

    BINDINGS = [Binding("escape", "cancel_edit", "Cancel", show=False)]

    def action_cancel_edit(self) -> None:
        self.app._cancel_cmdline_edit()  # type: ignore[attr-defined]


class MdViewerApp(App):
    CSS_PATH = "theme.css"

    # less/delta-style key map. Esc is `cancel` (never quit); quitting is `q` or
    # `:q`. Key *names* matter for the punctuation: see textual.keys
    # (`]`=right_square_bracket, `}`=right_curly_bracket, `:`=colon, etc.).
    BINDINGS = [
        # quit / command line / cancel
        Binding("q", "quit", "Quit", show=True),
        Binding("colon", "command", "Command", show=True),
        Binding("escape", "cancel", "Cancel", show=False),
        # scrolling (less)
        Binding("j,down", "scroll_down", "Down", show=False),
        Binding("k,up", "scroll_up", "Up", show=False),
        Binding("d,ctrl+d", "scroll_half_down", "Half page down", show=False),
        Binding("u,ctrl+u", "scroll_half_up", "Half page up", show=False),
        Binding("f,ctrl+f,pagedown", "page_down", "Page down", show=False),
        Binding("b,ctrl+b,pageup", "page_up", "Page up", show=False),
        Binding("g,less_than_sign", "scroll_home", "Top", show=False),
        Binding("G,greater_than_sign", "scroll_end", "Bottom", show=False),
        # search (less): / to search, n/N to step matches
        Binding("slash", "search", "Search", show=True),
        Binding("n", "next_match", "Next match", show=True),
        Binding("N", "prev_match", "Prev match", show=False),
        # structural navigation. Space/Shift+Space are the ergonomic, context-
        # aware pair (headings in prose, file headings + @@ hunks in a diff);
        # the bracket keys are explicit and always available (and `[`/`{` are the
        # reliable "previous" where a terminal can't send Shift+Space).
        Binding("space", "next_section", "Next section", show=False),
        Binding("shift+space", "prev_section", "Prev section", show=False),
        Binding("right_square_bracket", "next_heading", "Next heading", show=True),
        Binding("left_square_bracket", "prev_heading", "Prev heading", show=False),
        # Ctrl+]/Ctrl+[ narrow to level-2 (`##`) section headings. (Ctrl+[ is the
        # ESC byte in legacy terminals, so "prev H2" only works where the kitty
        # keyboard protocol is active; `[` stays the reliable all-heading prev.)
        Binding("ctrl+right_square_bracket", "next_h2", "Next section (H2)", show=False),
        Binding("ctrl+left_square_bracket", "prev_h2", "Prev section (H2)", show=False),
        Binding("right_curly_bracket", "next_hunk", "Next hunk", show=False),
        Binding("left_curly_bracket", "prev_hunk", "Prev hunk", show=False),
        # Horizontal scroll for a wide event flow (the visible EventFlow widget).
        # Plain left is link-back and `<`/`>` are home/end, so use shift+arrows.
        Binding("shift+right", "flow_scroll_right", "Flow right", show=False),
        Binding("shift+left", "flow_scroll_left", "Flow left", show=False),
        Binding("t", "open_toc", "TOC", show=True),
        # link history (b is page-up now, so back moves to Backspace/←)
        Binding("backspace,left", "go_back", "Back", show=True),
        # selection / AI
        Binding("v", "expand_selection", "Expand sel", show=True),
        Binding("V", "shrink_selection", "Shrink sel", show=False),
        Binding("h", "ask_ai", "Ask AI", show=True),
        # help
        Binding("question_mark", "help", "Help", show=True),
    ]

    def __init__(
        self,
        md_path: Path | None = None,
        *,
        content: str | None = None,
        base_dir: Path | None = None,
        diff_files: list[FileDiff] | None = None,
    ) -> None:
        super().__init__()
        self._history: list[tuple[Path, float]] = []
        # Parsed diff model when the document is a whole unified diff; used by
        # `_inject_diff_hunks` to render each ```diff placeholder fence as a
        # delta-styled `DiffHunk` (the model carries each hunk's file path so
        # code can be syntax-highlighted in its language).
        self._diff_files = diff_files
        # Semantic-selection ladder state (see mdview.selection). `_sel_scopes`
        # is the expansion ladder for the current anchor; `_sel_index` is the
        # active rung. All None/0 means no active semantic selection.
        self._sel_anchor: Widget | None = None
        self._sel_scopes: list[list[Widget]] | None = None
        self._sel_index: int = 0
        # マウス押下時のスクリーン座標。on_click でクリック(押下位置と一致)と
        # ドラッグ(不一致)を区別するために使う。ドラッグ時はフレームワークの
        # 自由選択を残したいので、on_click はセマンティック選択を適用しない。
        self._mouse_down_offset: Offset | None = None
        # `/` search state. `_search_query` is the last submitted pattern (so the
        # bar reopens prefilled); `_search_matches` is the matched blocks in
        # document order. While a search is active `n`/`N` walk the matches
        # (headings stay on `]`/`[`). `_search_index` is the current match
        # (highlighted distinctly so a jump is visible even when on-screen).
        self._search_query: str = ""
        # `_search_hits` is one entry per matched substring (block, offset span,
        # and the line index of the match within the block so n/N can scroll to
        # the exact line, not just the block top); `n`/`N` step through it one
        # occurrence at a time, with `_search_index` the current one.
        # `_search_matches` is the de-duped blocks that hold a hit (used to restore
        # whole blocks when clearing).
        self._search_hits: list[tuple[Widget, int, int, int]] = []
        self._search_matches: list[Widget] = []
        self._search_index: int = 0
        # The compiled pattern (for re-highlighting on n/N) and the per-block
        # originals captured before washing, so highlights can be undone cleanly.
        self._search_pattern: regex.Pattern[str] | None = None
        self._search_originals: dict[Widget, object] = {}
        # TemporaryDirectory has its own finalizer that runs at interpreter
        # shutdown; no atexit.register needed. Registering here would pin the
        # cleanup callback for the whole process even if .run() never fires,
        # leaking the tempdir.
        self._tempdir = tempfile.TemporaryDirectory(prefix="mdview-")
        # Section insight state (the `##` lightbulb → treasure feature). Set on
        # load when `claude` is present; `_insight_headings` maps a heading id to
        # its widget, `_insight_state` to its generation state. `_insight_running`
        # caps concurrency; the spinner timer animates running markers.
        self._insight_claude: str | None = None
        self._insight_headings: dict[str, MarkdownHeader] = {}
        self._insight_state: dict[str, _InsightState] = {}
        self._insight_running: int = 0
        self._insight_spinner_frame: int = 0
        self._insight_timer: Timer | None = None
        if content is not None:
            # stdin has no source directory, so relative images/links resolve
            # against base_dir (defaults to CWD). Stash the text in the tempdir
            # so the rest of the pipeline keeps working off a real path.
            stdin_file = Path(self._tempdir.name) / "stdin.md"
            stdin_file.write_text(content, encoding="utf-8")
            self._md_path = stdin_file
            self._md_dir = (base_dir or Path.cwd()).resolve()
            self._display_name = "(stdin)"
        else:
            self._md_path = md_path.resolve()
            self._md_dir = self._md_path.parent
            self._display_name = self._md_path.name

    def compose(self) -> ComposeResult:
        # open_links=False so we route anchors (#section) to goto_anchor
        # ourselves instead of letting Textual hand them to the OS browser.
        yield _MdViewer(show_table_of_contents=False, open_links=False)
        # The unified command line, docked at the bottom and hidden until `/` or
        # `:` (theme.css sets `display: none`; action_search/action_command flip
        # it on). less/vim-style: one editable field whose leading `/` or `:`
        # selects search vs command mode (see _run_cmdline); the match
        # count/status sits at the right.
        with Horizontal(id="cmdline-bar"):
            yield _CommandLine(placeholder="/ 検索   : コマンド", id="cmdline")
            yield Static("", id="cmdline-count")

    async def on_mount(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        self.title = self._display_name
        try:
            await viewer.document.load(self._md_path)
        except OSError as e:
            self.exit(message=f"mdview: failed to load {self._md_path}: {e}")
            return
        await self._inject_images()
        await self._inject_mermaid()
        await self._inject_diff_hunks()
        await self._inject_event_flows()
        await self._inject_section_insights()

    async def _inject_images(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        paragraphs = list(viewer.document.query(MarkdownParagraph))
        for paragraph in paragraphs:
            src = _paragraph_image_src(paragraph)
            if src is None:
                continue
            image_path = self._resolve_image_path(src)
            if image_path is None:
                continue
            try:
                image_widget = self._build_image_widget(image_path)
            except SvgRenderError:
                continue
            if image_widget is None:
                continue
            await viewer.document.mount(image_widget, after=paragraph)
            await paragraph.remove()

    async def _inject_mermaid(self) -> None:
        mmdc = find_mmdc()
        if mmdc is None:
            return
        viewer = self.query_one(MarkdownViewer)
        fences = [
            f for f in viewer.document.query(MarkdownFence) if (f.lexer or "").lower() == "mermaid"
        ]
        for fence in fences:
            image_widget = self._render_mermaid_fence(fence.code, mmdc)
            if image_widget is None:
                continue
            await viewer.document.mount(image_widget, after=fence)
            await fence.remove()

    async def _inject_diff_hunks(self) -> None:
        """Swap each ```diff fence for a delta-styled `DiffHunk` widget.

        For a whole-document diff the parsed model (`self._diff_files`) supplies
        each hunk and its file path (so code is highlighted in its language); the
        fences and the flattened hunks line up one-for-one because
        `diff_to_markdown` emits exactly one fence per hunk, in order. A ```diff
        fence authored inside ordinary Markdown has no model, so its body is
        parsed standalone and rendered without a known language.
        """
        viewer = self.query_one(MarkdownViewer)
        if self._diff_files is not None:
            # A file heading and its hunks read as one unit, so tag the headings
            # for the CSS that drops their bottom margin (the @@ hunk header then
            # sits directly under the file heading instead of after a blank row).
            for header in viewer.document.query(MarkdownHeader):
                header.add_class("diff-file")
        fences = [
            f for f in viewer.document.query(MarkdownFence) if (f.lexer or "").lower() == "diff"
        ]
        if not fences:
            return
        if self._diff_files is not None:
            pairs = [(hunk, file.path) for file in self._diff_files for hunk in file.hunks]
        else:
            pairs = [(parse_hunk_lines(f.code), None) for f in fences]
        for fence, (hunk, file_path) in zip(fences, pairs):
            await viewer.document.mount(DiffHunk(hunk, file_path=file_path), after=fence)
            await fence.remove()

    async def _inject_event_flows(self) -> None:
        """Swap each ```event-flow-svg fence for an `EventFlow` swimlane widget.

        The fence body is the EventStorming flow DSL; `parse_flow_dsl` turns it
        into the model, which `EventFlow` renders as colour-coded sticky-note
        swimlanes (horizontally scrollable). A fence whose body has no lanes
        (parse returns None) is left as a plain code block — degrade gracefully.
        The original DSL is stashed on the widget so selecting/Ask-AI'ing the
        flow yields readable source, not the box-art.
        """
        viewer = self.query_one(MarkdownViewer)
        fences = [
            f
            for f in viewer.document.query(MarkdownFence)
            if (f.lexer or "").lower() == "event-flow-svg"
        ]
        for fence in fences:
            flow = parse_flow_dsl(fence.code)
            if flow is None:
                continue
            await viewer.document.mount(EventFlow(flow, source=fence.code), after=fence)
            await fence.remove()

    async def _inject_section_insights(self) -> None:
        """Add a clickable 💡 to the right of each `##` heading.

        Clicking it asks `claude` to explain that section (with an SVG diagram)
        in the background; while running the 💡 spins, and on success it becomes
        a 📦 whose click opens the explanation. The whole feature is skipped when
        `claude` is absent (degrade to nothing) or for a whole-document diff
        (file headings aren't prose sections). The heading widget is left
        structurally untouched — only its rendered Content gains the marker — so
        navigation/TOC/selection keep working; a per-heading `get_selection`
        override keeps the marker out of copied/searched/AI'd text.
        """
        self._insight_claude = find_claude()
        if self._insight_claude is None or self._diff_files is not None:
            return
        for heading in self._headings_at_level(2):
            hid = heading.id
            if hid is None:
                continue
            heading._insight_base = heading._content
            heading.get_selection = types.MethodType(_insight_get_selection, heading)
            self._insight_headings[hid] = heading
            self._insight_state[hid] = _InsightState()
            self._apply_glyph(hid)
        # Sizes aren't known until after layout; reflow once to right-align.
        self.call_after_refresh(self._reflow_insight_glyphs)

    def _reset_insights(self) -> None:
        """Forget the previous document's insight markers (on navigation)."""
        self._insight_headings = {}
        self._insight_state = {}
        self._insight_spinner_frame = 0
        if self._insight_timer is not None:
            self._insight_timer.stop()
            self._insight_timer = None

    def action_section_insight(self, heading_id: str) -> None:
        """Handle a click on a heading's marker (routed via the Content `@click`).

        Done → open the saved explanation. Running → ignore. Otherwise start a
        generation, unless three are already in flight (then notify and refuse).
        """
        heading = self._insight_headings.get(heading_id)
        if heading is None:
            return
        state = self._insight_state[heading_id]
        if state.status == "running":
            return
        if state.status == "done":
            self.push_screen(
                SectionInsightScreen(
                    state.prose, state.svgs, tmpdir=Path(self._tempdir.name)
                )
            )
            return
        if self._insight_running >= _INSIGHT_MAX_CONCURRENT:
            self.notify(
                f"解説を生成中です（最大{_INSIGHT_MAX_CONCURRENT}件）", severity="warning"
            )
            return
        # Count synchronously here (not in the worker) so the cap is exact even
        # when clicks arrive faster than workers start.
        state.status = "running"
        self._insight_running += 1
        self._ensure_spinner()
        self._apply_glyph(heading_id)
        self._run_section_insight(heading)

    @work
    async def _run_section_insight(self, heading: MarkdownHeader) -> None:
        hid = heading.id
        try:
            viewer = self.query_one(MarkdownViewer)
            section = section_source(heading, viewer.document)
            document = viewer.document.source
            # A per-heading dir so concurrent runs never mix up their diagrams.
            svg_out_dir = Path(self._tempdir.name) / "section-svg" / str(hid)
            self._reset_svg_dir(svg_out_dir)
            try:
                result = await ask_claude(
                    section,
                    _INSIGHT_QUESTION,
                    document,
                    claude=self._insight_claude,
                    cwd=self._md_dir,
                    svg_out_dir=svg_out_dir,
                    concise_svg=True,
                    timeout=_INSIGHT_TIMEOUT_S,
                )
            except AiQueryError as e:
                if hid in self._insight_headings:
                    self._insight_state[hid].status = "error"
                    self.notify(f"解説の生成に失敗しました: {e}", severity="error")
            else:
                # SVGs come from two places: files Claude saved (the common case)
                # and any inlined into stdout. Prose is what's left.
                inline_svgs, prose = extract_svgs(result)
                saved = (
                    [
                        p.read_text(encoding="utf-8", errors="replace")
                        for p in sorted(svg_out_dir.glob("*.svg"))
                    ]
                    if svg_out_dir.exists()
                    else []
                )
                # Guard against navigation: if the heading is gone, drop the result.
                if hid in self._insight_headings:
                    st = self._insight_state[hid]
                    st.status = "done"
                    st.prose = prose or result
                    st.svgs = saved + inline_svgs
        finally:
            self._insight_running = max(0, self._insight_running - 1)
            if hid in self._insight_headings:
                self._apply_glyph(hid)

    @staticmethod
    def _reset_svg_dir(d: Path) -> None:
        """Start each run with an empty dir so a re-run doesn't re-collect stale SVGs."""
        if d.exists():
            for stale in d.glob("*.svg"):
                stale.unlink()
        d.mkdir(parents=True, exist_ok=True)

    def _ensure_spinner(self) -> None:
        if self._insight_timer is None:
            self._insight_timer = self.set_interval(0.12, self._tick_spinner)

    def _tick_spinner(self) -> None:
        self._insight_spinner_frame += 1
        running = [h for h, st in self._insight_state.items() if st.status == "running"]
        if not running:
            if self._insight_timer is not None:
                self._insight_timer.stop()
                self._insight_timer = None
            return
        for hid in running:
            self._apply_glyph(hid)

    def _reflow_insight_glyphs(self) -> None:
        for hid in self._insight_headings:
            self._apply_glyph(hid)

    def _apply_glyph(self, hid: str) -> None:
        heading = self._insight_headings.get(hid)
        if heading is None:
            return
        state = self._insight_state[hid]
        if state.status == "running":
            glyph = _INSIGHT_SPINNER[self._insight_spinner_frame % len(_INSIGHT_SPINNER)]
        else:
            glyph = _INSIGHT_GLYPHS[state.status]
        base = getattr(heading, "_insight_base", None)
        if base is None:
            return
        # Right-align the marker: pad from the title to the heading's right edge.
        # content_size is 0 before layout, so the first pass sits the marker just
        # after the title; _reflow_insight_glyphs / on_resize fix it up.
        pad = heading.content_size.width - cell_len(base.plain) - cell_len(glyph) - 1
        gap = " " * max(1, pad)
        suffix = Content.from_markup(f"{gap}[@click=app.section_insight('{hid}')]{glyph}[/]")
        heading.set_content(base + suffix)

    def _render_mermaid_fence(self, code: str, mmdc: str) -> Image | None:
        digest = hashlib.sha1(code.encode("utf-8")).hexdigest()[:12]
        png_path = Path(self._tempdir.name) / f"mermaid-{digest}.png"
        target_width_px = max(400, (self.size.width or 80) * 16)
        try:
            render_mermaid(code, png_path, mmdc=mmdc, width=target_width_px)
        except MermaidRenderError:
            return None
        return Image(png_path, classes="mdview-image")

    def _resolve_image_path(self, src: str) -> Path | None:
        if src.startswith(("http://", "https://", "data:")):
            return None
        candidate = (self._md_dir / src).resolve()
        if not candidate.exists():
            return None
        return candidate

    def _build_image_widget(self, image_path: Path) -> Image | ZoomableImage | None:
        suffix = image_path.suffix.lower()
        if suffix == ".svg":
            # Disambiguate two SVGs with the same basename in different dirs
            # by hashing the resolved absolute path.
            key = hashlib.sha1(str(image_path).encode("utf-8")).hexdigest()[:12]
            png_path = Path(self._tempdir.name) / f"{image_path.stem}-{key}.png"
            target_width_px = max(400, (self.size.width or 80) * 16)
            rasterize_svg(image_path, png_path, width_px=target_width_px)
            # Zoomable: click an SVG diagram to view it full-screen.
            return ZoomableImage(png_path)
        if suffix in _IMAGE_EXTS:
            return Image(image_path, classes="mdview-image")
        return None

    def on_markdown_link_clicked(self, event: Markdown.LinkClicked) -> None:
        href = event.href
        if href.startswith("#"):
            anchor = href[1:]
            if anchor:
                event.markdown.goto_anchor(anchor)
            else:
                # `[top](#)` convention — scroll to the top of the document.
                self.query_one(MarkdownViewer).scroll_home(animate=False)
            return
        if href.startswith(("http://", "https://", "mailto:", "data:")):
            self.open_url(href)
            return
        target = self._resolve_md_link(href)
        if target is not None:
            path, anchor = target
            self.run_worker(self._navigate_to(path, anchor), exclusive=True)
            return
        self.open_url(href)

    def _resolve_md_link(self, href: str) -> tuple[Path, str] | None:
        raw_path, _, anchor = href.partition("#")
        if not raw_path:
            return None
        decoded = unquote(raw_path)
        candidate = Path(decoded)
        if not candidate.is_absolute():
            candidate = self._md_dir / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            return None
        if candidate.suffix.lower() not in _MARKDOWN_EXTS:
            return None
        if not candidate.is_file():
            return None
        return candidate, anchor

    async def _navigate_to(self, path: Path, anchor: str) -> None:
        viewer = self.query_one(MarkdownViewer)
        # Capture pre-load state, but only commit it to history after load
        # succeeds. Otherwise a failed/cancelled load leaves a phantom entry
        # pointing at the file the user is still viewing.
        prev = (self._md_path, viewer.scroll_y)
        if await self._load_file(path, anchor):
            self._history.append(prev)

    async def _load_file(self, path: Path, anchor: str = "") -> bool:
        viewer = self.query_one(MarkdownViewer)
        try:
            await viewer.document.load(path)
        except OSError as e:
            self.notify(f"failed to load {path}: {e}", severity="error")
            return False
        self._md_path = path
        self._md_dir = path.parent
        self.title = path.name
        # The previous document's widgets are gone; drop any active search so
        # n/N don't step detached hits and the bar doesn't show a stale query.
        self._end_search()
        self._reset_insights()
        await self._inject_images()
        await self._inject_mermaid()
        await self._inject_diff_hunks()
        await self._inject_event_flows()
        await self._inject_section_insights()
        if anchor:
            self.call_after_refresh(viewer.document.goto_anchor, anchor)
        else:
            viewer.scroll_home(animate=False)
        return True

    def action_go_back(self) -> None:
        if not self._history:
            return
        prev_path, prev_scroll = self._history.pop()
        self.run_worker(self._load_and_restore(prev_path, prev_scroll), exclusive=True)

    async def _load_and_restore(self, path: Path, scroll_y: float) -> None:
        await self._load_file(path)
        viewer = self.query_one(MarkdownViewer)
        viewer.scroll_to(y=scroll_y, animate=False)

    def action_scroll_down(self) -> None:
        self.query_one(MarkdownViewer).scroll_relative(y=1, animate=False)

    def action_scroll_up(self) -> None:
        self.query_one(MarkdownViewer).scroll_relative(y=-1, animate=False)

    def action_scroll_half_down(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        viewer.scroll_relative(y=viewer.size.height // 2, animate=False)

    def action_scroll_half_up(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        viewer.scroll_relative(y=-(viewer.size.height // 2), animate=False)

    def action_page_down(self) -> None:
        # Less-style full page with one line of overlap for continuity.
        viewer = self.query_one(MarkdownViewer)
        viewer.scroll_relative(y=max(1, viewer.size.height - 1), animate=False)

    def action_page_up(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        viewer.scroll_relative(y=-max(1, viewer.size.height - 1), animate=False)

    def action_scroll_home(self) -> None:
        self.query_one(MarkdownViewer).scroll_home(animate=False)

    def action_scroll_end(self) -> None:
        self.query_one(MarkdownViewer).scroll_end(animate=False)

    def action_flow_scroll_right(self) -> None:
        self._scroll_visible_flow(1)

    def action_flow_scroll_left(self) -> None:
        self._scroll_visible_flow(-1)

    def _scroll_visible_flow(self, direction: int) -> None:
        """Scroll the on-screen event flow horizontally (no-op if none visible)."""
        flow = self._visible_event_flow()
        if flow is not None:
            flow.scroll_relative(x=direction * 8, animate=False)

    def _visible_event_flow(self) -> EventFlow | None:
        """The first `EventFlow` overlapping the viewer's viewport, or None."""
        viewer = self.query_one(MarkdownViewer)
        top, bottom = viewer.region.y, viewer.region.bottom
        for flow in viewer.document.query(EventFlow):
            region = flow.region
            if region.area and region.bottom > top and region.y < bottom:
                return flow
        return None

    def action_help(self) -> None:
        # `?` / `:h` open the shortcut cheat-sheet. If it's already up (re-press
        # `?`), HelpScreen's own `question_mark` binding dismisses it first, so
        # this only ever pushes when none is open.
        if not isinstance(self.screen, HelpScreen):
            self.push_screen(HelpScreen())

    def action_ask_ai(self) -> None:
        selection = self.screen.get_selected_text()
        if not selection or not selection.strip():
            self.notify("質問するテキストを選択してください", severity="warning")
            return
        claude = find_claude()
        if claude is None:
            self.notify("claude CLI が見つかりません", severity="error")
            return
        document = self.query_one(MarkdownViewer).document.source
        self.push_screen(
            AskAiScreen(
                selection,
                document,
                claude=claude,
                cwd=self._md_dir,
                tmpdir=Path(self._tempdir.name),
            )
        )

    def action_open_toc(self) -> None:
        # The TOC opens as a wide centered modal (TocScreen) rather than the
        # docked sidebar, which truncated long headings (e.g. a diff's file
        # paths). The viewer keeps a hidden MarkdownTableOfContents purely as the
        # data source that Textual populates on load; we hand its data to the
        # modal.
        viewer = self.query_one(MarkdownViewer)
        toc_data = viewer.query_one(MarkdownTableOfContents).table_of_contents
        if not toc_data:
            return
        self.push_screen(TocScreen(viewer, toc_data))

    def action_next_match(self) -> None:
        # `n` steps search matches; no-op when no search is active.
        if self._search_hits:
            self._step_match(1)

    def action_prev_match(self) -> None:
        if self._search_hits:
            self._step_match(-1)

    def action_next_heading(self) -> None:
        self._jump_to(self._all_headings(), direction=1)

    def action_prev_heading(self) -> None:
        self._jump_to(self._all_headings(), direction=-1)

    def action_next_h2(self) -> None:
        self._jump_to(self._headings_at_level(2), direction=1)

    def action_prev_h2(self) -> None:
        self._jump_to(self._headings_at_level(2), direction=-1)

    def action_next_hunk(self) -> None:
        self._jump_to(list(self.query_one(MarkdownViewer).document.query(DiffHunk)), direction=1)

    def action_prev_hunk(self) -> None:
        self._jump_to(list(self.query_one(MarkdownViewer).document.query(DiffHunk)), direction=-1)

    def action_next_section(self) -> None:
        self._jump_to(self._section_targets(), direction=1)

    def action_prev_section(self) -> None:
        self._jump_to(self._section_targets(), direction=-1)

    def _section_targets(self) -> list[Widget]:
        """Space/Shift+Space targets: headings, plus every `@@` hunk so a diff
        steps file boundary → hunk → hunk in document order. In prose with no
        diff there are no DiffHunks, so this is just the headings."""
        viewer = self.query_one(MarkdownViewer)
        return self._all_headings() + list(viewer.document.query(DiffHunk))

    def _all_headings(self) -> list[Widget]:
        return list(self.query_one(MarkdownViewer).document.query(MarkdownHeader))

    def _headings_at_level(self, level: int) -> list[Widget]:
        # Textual mounts MarkdownH1..H6, each carrying a `LEVEL` class attr; a
        # diff's `## @ file` headings are H2, so Opt+]/[ walk files there.
        return [h for h in self._all_headings() if getattr(h, "LEVEL", None) == level]

    def _jump_to(self, targets: list[Widget], *, direction: int) -> None:
        viewer = self.query_one(MarkdownViewer)
        if not targets:
            return
        positions = sorted(w.virtual_region.y for w in targets)
        current = viewer.scroll_y
        threshold = 1  # tolerate sub-cell rounding so "next" doesn't snap to current
        if direction > 0:
            target_y = next((y for y in positions if y > current + threshold), positions[-1])
        else:
            target_y = next(
                (y for y in reversed(positions) if y < current - threshold), positions[0]
            )
        viewer.scroll_to(y=target_y, animate=False)

    def action_search(self) -> None:
        """Open the command line in search mode (`/`), prefilled with the last query."""
        self._open_cmdline("/" + self._search_query)

    def action_command(self) -> None:
        """Open the command line in command mode (`:`)."""
        self._open_cmdline(":")

    def _open_cmdline(self, initial: str) -> None:
        self.query_one("#cmdline-bar").display = True
        box = self.query_one("#cmdline", Input)
        box.value = initial
        box.focus()
        box.cursor_position = len(initial)  # caret after the prefix, ready to type

    def action_cancel(self) -> None:
        """Esc with nothing focused: cancel transient state; never quit.

        Esc while editing the command line is handled by `_CommandLine`'s own
        binding (and a modal's Esc dismisses it). Here Esc only reaches the App
        on the base screen, where it clears any active search *and* drops the
        current selection — resetting the semantic-selection ladder so the next
        `v`/click starts small again. With nothing active it's a deliberate
        no-op; it must never exit the app.
        """
        if self._search_hits or self.query_one("#cmdline-bar").display:
            self._end_search()
        # Clear any selection (semantic or a raw drag) and reset the ladder, so
        # the next expand/click begins from the smallest block.
        self.screen.clear_selection()
        self._reset_selection_state()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "cmdline":
            self._run_cmdline(event.value)
        # else: ignore an Ask AI Input.Submitted bubbling up.

    def _run_cmdline(self, raw: str) -> None:
        """Dispatch the command line by its leading character: `:` → command,
        anything else → search (a leading `/` is the prompt and is stripped)."""
        if raw.startswith(":"):
            self._run_command(raw[1:])
            return
        query = raw[1:] if raw.startswith("/") else raw
        self._search_query = query
        self._run_search()
        # Normalise the status display to `/query` and drop focus so n/N reach
        # the App's bindings (the viewer is can_focus=False, so we blur rather
        # than focus it). The bar stays as a status line while a search is
        # active; an empty query clears it (see _run_search).
        self.query_one("#cmdline", Input).value = "/" + query
        self.set_focus(None)

    def _run_command(self, raw: str) -> None:
        """Dispatch a `:` command (text after the colon), then close the line."""
        command = parse_command(raw)
        self.query_one("#cmdline-bar").display = False
        self.set_focus(None)
        if command == "quit":
            self.exit()  # exit() is sync; App.action_quit is a coroutine
        elif command == "help":
            self.action_help()
        elif raw.strip():
            self.notify(f"未知のコマンド: :{raw.strip()}", severity="warning")

    def _cancel_cmdline_edit(self) -> None:
        """Esc while editing: stop editing without quitting. If a search is
        active, restore its `/query` status line; otherwise hide the bar."""
        if self._search_hits:
            self.query_one("#cmdline", Input).value = "/" + self._search_query
        else:
            self.query_one("#cmdline-bar").display = False
        self.set_focus(None)

    def _run_search(self) -> None:
        """Recompute hits for `_search_query` and focus the first one.

        A *hit* is one matched substring (block + offset span); `n`/`N` step
        through hits one at a time, so a block with several matches is walked
        occurrence-by-occurrence, not skipped in one jump. Every hit is washed in
        colour; the current one is brighter. `_search_matches` is the de-duped
        list of blocks that contain a hit (for whole-block restore). An empty
        query clears the search (`n`/`N` then become no-ops until the next `/`).
        """
        viewer = self.query_one(MarkdownViewer)
        count = self.query_one("#cmdline-count", Static)
        self._clear_search_highlights()
        pattern = compile_query(self._search_query)
        self._search_pattern = pattern
        if pattern is None:
            self._reset_search_state()
            count.update("")
            self.query_one("#cmdline-bar").display = False
            return
        hits: list[tuple[Widget, int, int, int]] = []
        widgets: list[Widget] = []
        deadline = monotonic() + _SEARCH_BUDGET_S
        try:
            for w in viewer.document.query("*"):
                if not isinstance(w, ATOMIC_BLOCKS):
                    continue
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError
                text = _search_text(w)
                spans = [
                    m.span()
                    for m in pattern.finditer(text, timeout=remaining)
                    if m.end() > m.start()
                ]
                if spans:
                    widgets.append(w)
                    # line index of each match within the block, so n/N can scroll
                    # to the matched line (preformatted blocks are one row per line).
                    hits.extend((w, s, e, text.count("\n", 0, s)) for s, e in spans)
        except TimeoutError:
            # A pathological pattern (catastrophic backtracking) blew the budget.
            self._reset_search_state()
            count.update("パターンが複雑すぎます")
            self.notify("検索パターンが複雑すぎます", severity="warning")
            return
        self._search_hits = hits
        self._search_matches = widgets
        if not hits:
            self._search_index = 0
            count.update("一致なし")
            return
        for w in widgets:
            self._paint_widget(w, pattern, current_span=None)
        # Start at the first hit whose block is at/below the current viewport.
        current = viewer.scroll_y
        self._search_index = next(
            (i for i, hit in enumerate(hits) if hit[0].virtual_region.y > current + 1), 0
        )
        self._focus_current()

    def _step_match(self, direction: int) -> None:
        """Advance to the next/previous hit, wrapping around the ends."""
        if not self._search_hits:
            return
        prev = self._search_index
        self._search_index = (prev + direction) % len(self._search_hits)
        self._focus_current(prev_index=prev)

    def _focus_current(self, prev_index: int | None = None) -> None:
        """Brighten the current hit, scroll its block into view, show position.

        *prev_index* (when stepping) has its block repainted with every hit in the
        subtler wash, so only one occurrence ever wears the current colour.
        """
        viewer = self.query_one(MarkdownViewer)
        hits = self._search_hits
        pattern = self._search_pattern
        if not hits or pattern is None:
            return
        widget, start, end, line = hits[self._search_index]
        if prev_index is not None and 0 <= prev_index < len(hits):
            prev_widget = hits[prev_index][0]
            if prev_widget is not widget:
                self._paint_widget(prev_widget, pattern, current_span=None)
        for w in viewer.document.query(".search-current"):
            w.remove_class("search-current")
        widget.add_class("search-current")  # marker (no CSS); the wash is per-word
        self._paint_widget(widget, pattern, current_span=(start, end))
        # Scroll to the matched line within the block (not just the block top), so
        # stepping through hits inside a tall block (a long fence/diff) still moves
        # the view. Keep a couple of rows of lead-in for context.
        target_y = max(0, widget.virtual_region.y + line - 2)
        viewer.scroll_to(y=target_y, animate=False)
        self.query_one("#cmdline-count", Static).update(
            f"{self._search_index + 1}/{len(hits)} 件"
        )

    def _paint_widget(
        self, widget: Widget, pattern: regex.Pattern[str], *, current_span: tuple[int, int] | None
    ) -> None:
        """Wash every match in *widget* subtly; brighten *current_span* if given."""
        if isinstance(widget, DiffHunk):
            text = render_hunk(widget._hunk, file_path=widget._file_path)
            text.highlight_regex(pattern, _MATCH_HL)
            if current_span is not None:
                text.stylize(_CURRENT_HL, *current_span)
            widget.update(text)
        elif isinstance(widget, MarkdownFence):
            content = widget._highlighted_code.highlight_regex(pattern, style=_MATCH_HL)
            if current_span is not None:
                content = content.stylize(_CURRENT_HL, *current_span)
            # The Label can be absent in some fence states — Textual's own
            # MarkdownFence.set_content guards the same query, so we do too.
            with suppress(NoMatches):
                widget.query_one("#code-content", Label).update(content)
        elif isinstance(widget, MarkdownBlock):
            original = self._search_originals.setdefault(widget, widget._content)
            content = original.highlight_regex(pattern, style=_MATCH_HL)
            if current_span is not None:
                content = content.stylize(_CURRENT_HL, *current_span)
            widget.set_content(content)

    def _restore_block(self, widget: Widget) -> None:
        """Undo `_paint_widget`, returning *widget* to its unsearched render."""
        if isinstance(widget, DiffHunk):
            widget.update(render_hunk(widget._hunk, file_path=widget._file_path))
        elif isinstance(widget, MarkdownFence):
            with suppress(NoMatches):
                widget.query_one("#code-content", Label).update(widget._highlighted_code)
        elif isinstance(widget, MarkdownBlock):
            original = self._search_originals.get(widget)
            if original is not None:
                widget.set_content(original)

    def _reset_search_state(self) -> None:
        self._search_hits = []
        self._search_matches = []
        self._search_index = 0

    def _clear_search_highlights(self) -> None:
        for widget in self._search_matches:
            self._restore_block(widget)
        self._search_originals.clear()
        self._reset_search_state()
        for w in self.query_one(MarkdownViewer).document.query(".search-current"):
            w.remove_class("search-current")

    def _end_search(self) -> None:
        """Drop any active search on document navigation.

        The old document's matched widgets are gone with the swapped-out tree, so
        there is nothing to restore — just forget the stale hits/highlights and
        hide the bar (the matched-widget refs would otherwise leave `n`/`N`
        stepping detached widgets in the new document). `_search_query` is kept so
        `/` reopens prefilled.
        """
        self._reset_search_state()
        self._search_originals.clear()
        self._search_pattern = None
        self.query_one("#cmdline-count", Static).update("")
        self.query_one("#cmdline-bar").display = False

    def on_resize(self, event: events.Resize) -> None:
        # Re-right-align the section-insight markers when the width changes.
        if self._insight_headings:
            self.call_after_refresh(self._reflow_insight_glyphs)

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

    def action_expand_selection(self) -> None:
        """Keyboard expand: grow one rung, starting at the top visible block."""
        if self._sel_scopes is not None:
            self._sel_index = min(self._sel_index + 1, len(self._sel_scopes) - 1)
        else:
            leaf = self._first_visible_block()
            if leaf is None:
                return
            self._start_selection(leaf)
        self._apply_scope(self._sel_scopes[self._sel_index])

    def action_shrink_selection(self) -> None:
        """Keyboard shrink: go down one rung, or clear at the smallest block."""
        if self._sel_scopes is None:
            return
        if self._sel_index > 0:
            self._sel_index -= 1
            self._apply_scope(self._sel_scopes[self._sel_index])
        else:
            self.screen.clear_selection()
            self._reset_selection_state()

    def _start_selection(self, leaf: Widget) -> None:
        document = self.query_one(MarkdownViewer).document
        self._sel_scopes = build_scopes(leaf, document)
        self._sel_index = 0
        self._sel_anchor = leaf

    def _reset_selection_state(self) -> None:
        self._sel_anchor = None
        self._sel_scopes = None
        self._sel_index = 0

    def _apply_scope(self, roots: list[Widget]) -> None:
        """Select each root widget and all of its descendants, in document order."""
        selections: dict[Widget, Selection] = {}
        for root in roots:
            selections[root] = SELECT_ALL
            for descendant in root.query("*"):
                selections[descendant] = SELECT_ALL
        self.screen.selections = selections

    def _first_visible_block(self) -> Widget | None:
        """The first atomic Markdown block overlapping the viewer's viewport."""
        viewer = self.query_one(MarkdownViewer)
        top = viewer.region.y
        bottom = viewer.region.bottom
        for node in viewer.document.query("*"):
            if isinstance(node, ATOMIC_BLOCKS):
                region = node.region
                if region.area and region.bottom > top and region.y < bottom:
                    return node
        return None


def _search_text(widget: Widget) -> str:
    """Plain text of a rendered block, for `/` search matching *and* highlighting.

    The offsets `pattern.finditer` returns here are used to colour the matched
    substrings, so this must be the very text those colours land on: a code
    fence's syntax-highlighted plain (== its raw code), a `DiffHunk`'s *rendered*
    text (gutter included — `@@` headers and code still match, and offsets line
    up with what's drawn), and every other Markdown block's rendered `Content`
    (heading text without the leading `##`, etc.).

    Known limitation: a `MarkdownTable`'s own `_content` is empty (its cell text
    lives in child `MarkdownTableContent` widgets), so table cell text is not
    searchable. Highlighting it would mean re-rendering the table's cells, which
    isn't worth the complexity here.
    """
    if isinstance(widget, DiffHunk):
        return render_hunk(widget._hunk, file_path=widget._file_path).plain
    if isinstance(widget, MarkdownFence):
        return widget._highlighted_code.plain
    if isinstance(widget, MarkdownBlock):
        # A section-insight heading carries its clean pre-marker content in
        # `_insight_base`; search that so the 💡/📦 marker isn't matched and the
        # offsets still line up with the rendered (marker-suffixed) Content.
        base = getattr(widget, "_insight_base", None)
        return (base if base is not None else widget._content).plain
    return ""


def _paragraph_image_src(paragraph: MarkdownParagraph) -> str | None:
    """Return the image src if the paragraph contains *only* one image, else None."""
    token: Token | None = paragraph._inline_token
    if token is None or token.children is None:
        return None
    images = [c for c in token.children if c.type == "image"]
    if len(images) != 1:
        return None
    others = [
        c
        for c in token.children
        if c.type not in ("image", "softbreak", "hardbreak")
        and not (c.type == "text" and not c.content.strip())
    ]
    if others:
        return None
    return images[0].attrs.get("src") or None
