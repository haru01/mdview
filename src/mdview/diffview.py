"""Render a parsed diff hunk in a `delta`-like style as a Rich `Text`.

Pure and framework-free: produces Rich renderables that both the TUI
(`mdview.diff_widget.DiffHunk`, which returns the `Text` from its `render`) and
the non-TTY path (`mdview.render.print_diff`) consume. A single `Text` keeps the
hunk text-selectable in Textual (its `Widget.get_selection` extracts from
`Content`/`Text`), while still carrying per-line background bars and per-language
syntax highlighting.

Layout per line: ``{old# } {new# } {marker} {code}`` — a two-column line-number
gutter, the `+`/`-`/space marker (kept so a copied/selected diff stays valid),
then the code, syntax-highlighted in the file's language. Added lines get a
green background bar, removed lines a red one.
"""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

from mdview.diff import FileDiff, Hunk, looks_like_diff, parse_diff, parse_hunk_lines
from mdview.palette import DIFF_ADD_BG, DIFF_DEL_BG, DIFF_FILE_RULE

# Background bars for changed lines (dark, low-saturation so syntax fg stays
# readable). Exposed as constants so tests and themes can reference them.
ADD_BG = DIFF_ADD_BG
DEL_BG = DIFF_DEL_BG
GUTTER_STYLE = "dim"
# The `@@` hunk-header line and the non-TTY file banner follow the accent hue.
HEADER_STYLE = f"dim {DIFF_FILE_RULE}"
_SYNTAX_THEME = "ansi_dark"


def hunk_plain_text(hunk: Hunk) -> str:
    """The selectable / Ask-AI text for a hunk: its raw unified-diff form."""
    return hunk.raw


def guess_lexer(path: str | None) -> str | None:
    """Best-effort Pygments lexer name from a file path (None → no highlight)."""
    if not path:
        return None
    try:
        return Syntax.guess_lexer(path)
    except Exception:
        return None


def _highlight(code: str, lexer: str | None) -> Text:
    """Syntax-highlight one code line, with no competing background colour."""
    if not lexer:
        return Text(code)
    try:
        highlighted = Syntax(
            code, lexer, theme=_SYNTAX_THEME, background_color="default"
        ).highlight(code)
    except Exception:
        return Text(code)
    if highlighted.plain.endswith("\n"):  # Syntax.highlight appends a newline
        highlighted = highlighted[:-1]
    return highlighted


def _gutter_width(hunk: Hunk) -> int:
    numbers = [n for ln in hunk.lines for n in (ln.old_no, ln.new_no) if n is not None]
    return max((len(str(n)) for n in numbers), default=1)


def render_hunk(hunk: Hunk, *, file_path: str | None = None) -> Text:
    """Render *hunk* as a delta-styled Rich `Text`."""
    lexer = guess_lexer(file_path)
    width = _gutter_width(hunk)
    lines: list[Text] = []

    if hunk.header:
        lines.append(Text(hunk.header, style=HEADER_STYLE))

    for ln in hunk.lines:
        old = f"{ln.old_no:>{width}}" if ln.old_no is not None else " " * width
        new = f"{ln.new_no:>{width}}" if ln.new_no is not None else " " * width
        marker = {"add": "+", "del": "-"}.get(ln.kind, " ")
        line = Text()
        line.append(f"{old} {new} ", style=GUTTER_STYLE)
        line.append(f"{marker} ")
        line.append_text(_highlight(ln.text, lexer))
        lines.append(line)

    width_cells = max((line.cell_len for line in lines), default=0)
    for line, ln in _zip_lines(lines, hunk):
        if line.cell_len < width_cells:
            line.pad_right(width_cells - line.cell_len)
        if ln is not None and ln.kind == "add":
            line.stylize(f"on {ADD_BG}")
        elif ln is not None and ln.kind == "del":
            line.stylize(f"on {DEL_BG}")

    return Text("\n").join(lines)


def _zip_lines(lines: list[Text], hunk: Hunk):
    """Pair rendered lines with their source DiffLine (header line → None)."""
    offset = 1 if hunk.header else 0
    for i, line in enumerate(lines):
        source = hunk.lines[i - offset] if i >= offset else None
        yield line, source


def render_file(file: FileDiff) -> RenderableType:
    """A file's delta-styled diff for the non-TTY path: banner + hunks."""
    title = f"{file.path}{' (' + file.status + ')' if file.status else ''}"
    parts: list[RenderableType] = [Rule(title, style=DIFF_FILE_RULE)]
    if file.binary_note:
        parts.append(Text(file.binary_note, style="dim"))
    for hunk in file.hunks:
        parts.append(render_hunk(hunk, file_path=file.path))
        parts.append(Text())  # blank line between hunks
    return Group(*parts)


def render_diff(files: list[FileDiff]) -> RenderableType:
    """The whole diff, delta-styled, for the non-TTY path."""
    return Group(*(render_file(file) for file in files))


def is_diff_text(text: str) -> bool:
    """Whether a selection should get the delta look — a unified diff, or a bare
    ``@@`` hunk (which is what a selected `DiffHunk` yields) — rather than being
    re-rendered as Markdown."""
    return looks_like_diff(text) or text.lstrip().startswith("@@")


def render_selection(text: str) -> RenderableType:
    """Delta-style render of a *diff* selection for the Ask AI full-text popup.

    The caller gates on `is_diff_text`; non-diff selections are re-rendered with
    a Markdown widget instead (so they match the main view's colours/spacing),
    which is why this only handles the diff case.
    """
    files = parse_diff(text)
    if files:
        return render_diff(files)
    return render_hunk(parse_hunk_lines(text))
