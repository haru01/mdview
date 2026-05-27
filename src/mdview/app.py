from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from urllib.parse import unquote

from markdown_it.token import Token
from pygments.token import Generic
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.highlight import HighlightTheme, highlight
from textual.widgets import Markdown, MarkdownViewer, Tree
from textual.widgets._markdown import (
    MarkdownFence,
    MarkdownHeader,
    MarkdownParagraph,
    MarkdownTableOfContents,
)
from textual_image.widget import Image

from mdview.ai import find_claude
from mdview.ask_ai import AskAiScreen
from mdview.mermaid import MermaidRenderError, find_mmdc, render_mermaid
from mdview.svg import SvgRenderError, rasterize_svg


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_MARKDOWN_EXTS = {".md", ".markdown", ".mdown", ".mkd"}


class _DiffHighlightTheme(HighlightTheme):
    """Syntax theme that colours diff added/removed lines.

    Textual's base theme leaves ``Generic.Inserted``/``Generic.Deleted``
    unstyled, so a ```diff fence shows +/- lines in the default colour. We map
    them to the semantic success/error colours so diffs read like a diff.
    """

    STYLES = {
        **HighlightTheme.STYLES,
        Generic.Inserted: "$text-success",
        Generic.Deleted: "$text-error",
    }


class _MdViewer(MarkdownViewer):
    """MarkdownViewer that skips the built-in CWD-based link handler.

    Why: the base class loads `[..](other.md)` via its navigator, which resolves
    against the process CWD instead of the current document's directory. We
    route link clicks ourselves from the App so paths resolve relative to the
    file being viewed.
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
        Binding("n", "next_heading", "Next heading", show=True),
        Binding("p", "prev_heading", "Prev heading", show=True),
        Binding("t", "toggle_toc", "TOC", show=True),
        Binding("b,left", "go_back", "Back", show=True),
        Binding("a", "ask_ai", "Ask AI", show=True),
        Binding("h,question_mark", "toggle_help", "Help", show=True),
    ]

    def __init__(
        self,
        md_path: Path | None = None,
        *,
        content: str | None = None,
        base_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._history: list[tuple[Path, float]] = []
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
        self._recolor_diff_fences()

    def _recolor_diff_fences(self) -> None:
        """Re-highlight ```diff fences with a theme that colours +/- lines.

        cli.py rewrites a piped/loaded diff into Markdown with ```diff fences;
        here we restyle them since Textual's default theme leaves +/- uncoloured.
        """
        viewer = self.query_one(MarkdownViewer)
        for fence in viewer.document.query(MarkdownFence):
            if (fence.lexer or "").lower() == "diff":
                fence.set_content(
                    highlight(fence.code, language="diff", theme=_DiffHighlightTheme)
                )

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

    def _build_image_widget(self, image_path: Path) -> Image | None:
        suffix = image_path.suffix.lower()
        if suffix == ".svg":
            # Disambiguate two SVGs with the same basename in different dirs
            # by hashing the resolved absolute path.
            key = hashlib.sha1(str(image_path).encode("utf-8")).hexdigest()[:12]
            png_path = Path(self._tempdir.name) / f"{image_path.stem}-{key}.png"
            target_width_px = max(400, (self.size.width or 80) * 16)
            rasterize_svg(image_path, png_path, width_px=target_width_px)
            return Image(png_path, classes="mdview-image")
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
        self._recolor_diff_fences()
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

    def action_toggle_toc(self) -> None:
        viewer = self.query_one(MarkdownViewer)
        viewer.show_table_of_contents = not viewer.show_table_of_contents
        if viewer.show_table_of_contents:
            # Focus the TOC's inner Tree so j/k/↑/↓ navigate it immediately.
            # call_after_refresh: the TOC widget mounts on the next layout pass.
            self.call_after_refresh(self._focus_toc)
        else:
            viewer.document.focus()

    def _focus_toc(self) -> None:
        try:
            toc = self.query_one(MarkdownTableOfContents)
        except NoMatches:
            return
        try:
            toc.query_one(Tree).focus()
        except NoMatches:
            return

    def action_next_heading(self) -> None:
        self._jump_heading(direction=1)

    def action_prev_heading(self) -> None:
        self._jump_heading(direction=-1)

    def _jump_heading(self, *, direction: int) -> None:
        viewer = self.query_one(MarkdownViewer)
        headings = list(viewer.document.query(MarkdownHeader))
        if not headings:
            return
        positions = sorted(h.virtual_region.y for h in headings)
        current = viewer.scroll_y
        threshold = 1  # tolerate sub-cell rounding so "next" doesn't snap to current
        if direction > 0:
            target_y = next((y for y in positions if y > current + threshold), positions[-1])
        else:
            target_y = next(
                (y for y in reversed(positions) if y < current - threshold), positions[0]
            )
        viewer.scroll_to(y=target_y, animate=False)


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
