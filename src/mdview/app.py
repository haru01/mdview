from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from urllib.parse import unquote

from markdown_it.token import Token
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.selection import SELECT_ALL, Selection
from textual.widget import Widget
from textual.widgets import Markdown, MarkdownViewer
from textual.widgets._markdown import (
    MarkdownFence,
    MarkdownHeader,
    MarkdownParagraph,
    MarkdownTableOfContents,
)
from textual_image.widget import Image

from mdview.ai import find_claude
from mdview.ask_ai import AskAiScreen
from mdview.diff import FileDiff, parse_hunk_lines
from mdview.diff_widget import DiffHunk
from mdview.image_zoom import ZoomableImage
from mdview.mermaid import MermaidRenderError, find_mmdc, render_mermaid
from mdview.selection import ATOMIC_BLOCKS, build_scopes, find_leaf_block
from mdview.svg import SvgRenderError, rasterize_svg
from mdview.toc import TocScreen


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_MARKDOWN_EXTS = {".md", ".markdown", ".mdown", ".mkd"}


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


class MdViewerApp(App):
    CSS_PATH = "theme.css"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("escape", "quit", "Quit", show=False),
        Binding("j,down", "scroll_down", "Down", show=False),
        Binding("k,up", "scroll_up", "Up", show=False),
        Binding("ctrl+d", "scroll_half_down", "Half page down", show=False),
        Binding("ctrl+u", "scroll_half_up", "Half page up", show=False),
        Binding("g", "scroll_home", "Top", show=False),
        Binding("G", "scroll_end", "Bottom", show=False),
        Binding("n", "next_heading", "Next file", show=True),
        Binding("p", "prev_heading", "Prev file", show=True),
        Binding("s", "next_hunk", "Next hunk", show=True),
        Binding("S", "prev_hunk", "Prev hunk", show=False),
        Binding("t", "open_toc", "TOC", show=True),
        Binding("b,left", "go_back", "Back", show=True),
        Binding("v", "expand_selection", "Expand sel", show=True),
        Binding("V", "shrink_selection", "Shrink sel", show=False),
        Binding("h", "ask_ai", "Ask AI", show=True),
        Binding("question_mark", "toggle_help", "Help", show=True),
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
        # TemporaryDirectory has its own finalizer that runs at interpreter
        # shutdown; no atexit.register needed. Registering here would pin the
        # cleanup callback for the whole process even if .run() never fires,
        # leaking the tempdir.
        self._tempdir = tempfile.TemporaryDirectory(prefix="mdview-")
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
        await self._inject_images()
        await self._inject_mermaid()
        await self._inject_diff_hunks()
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

    def action_scroll_home(self) -> None:
        self.query_one(MarkdownViewer).scroll_home(animate=False)

    def action_scroll_end(self) -> None:
        self.query_one(MarkdownViewer).scroll_end(animate=False)

    def action_toggle_help(self) -> None:
        from textual.widgets import HelpPanel

        existing = self.screen.query(HelpPanel)
        if existing:
            existing.remove()
        else:
            self.screen.mount(HelpPanel())

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

    def action_next_heading(self) -> None:
        self._jump_to(MarkdownHeader, direction=1)

    def action_prev_heading(self) -> None:
        self._jump_to(MarkdownHeader, direction=-1)

    def action_next_hunk(self) -> None:
        self._jump_to(DiffHunk, direction=1)

    def action_prev_hunk(self) -> None:
        self._jump_to(DiffHunk, direction=-1)

    def _jump_to(self, widget_type: type[Widget], *, direction: int) -> None:
        viewer = self.query_one(MarkdownViewer)
        targets = list(viewer.document.query(widget_type))
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

    def on_click(self, event: events.Click) -> None:
        """Mouse-driven semantic selection.

        The first click on a block selects it; clicking the same block again
        expands one rung along the Markdown structure. Clicking a different
        block restarts the ladder there. (A stationary click clears any drag
        selection in the framework's MouseUp handler first; we then set ours.)
        """
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
