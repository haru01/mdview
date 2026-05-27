"""Render an EventStorming :class:`~mdview.eventflow.Flow` as a Rich ``Text``.

Pure and framework-free (mirrors ``diffview`` for diffs): produces one multi-line
``Text`` of colour-coded sticky-note boxes laid out left-to-right within each
swimlane (bounded-context) row. The Textual wrapper
(``mdview.eventflow_widget.EventFlow``) drops this ``Text`` into a horizontally
scrollable container, so the flow is drawn at its natural width and never wraps.

Layout per flow::

    flow: <title>

    <bcname> │ <description>
    ─────────┼───────────────────────────────
             │ ┌Actor─┐    ┌Command──┐   ┌Event────┐
             │ │主催者│ ─> │作成      │─> │作成された│ ╌╌>
             │ └──────┘    └─────────┘   └─────────┘

Each note is a 3-row box: the kind label (Actor/Command/…) sits in the top
border, the note label in the middle. A lane ending in ``>>`` trails the async
arrow; a Join (``&>>``) trails the Join mark; a fan-out (``*>``) note wears a
``×N`` badge.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text

from mdview.eventflow import KIND_LABEL, Flow, Lane, Note

# Per-kind accent (border + kind label + text). EventStorming's sticky-note
# colour convention — intentionally outside theme.css's coral-only palette,
# because the colours carry meaning here (yellow=actor, blue=command, …).
KIND_STYLE = {
    "actor": "#e3c84b",  # yellow
    "command": "#6db3f2",  # blue
    "event": "#e8883a",  # orange
    "policy": "#c490e0",  # purple
    "readmodel": "#74c98a",  # green
}
# Bounded-context (lane name) colours, cycled per unique BC.
LANE_COLORS = ["#90a4ae", "#b0bec5", "#80cbc4", "#9fa8da", "#bcaaa4"]

SYNC_ARROW = "─>"  # same transaction (within a lane)
ASYNC_ARROW = "╌╌>"  # cross-lane async transition (lane ends in `>>`)
JOIN_MARK = "═Σ═>"  # Join (`&>>`): N→1 convergence (BPMN sync bar)
FANOUT_BADGE = "×N"  # BULK fork (`*>`): N parallel instances

_GUTTER_SEP_STYLE = "#5c6b73"
_ASYNC_STYLE = "#c490e0"
_JOIN_STYLE = "bold #cfd8dc"
_TITLE_STYLE = "bold #d97757"

_MIN_INNER = 4
_MAX_INNER = 24


def render_flow(flow: Flow) -> Text:
    """Render *flow* as a multi-line Rich ``Text`` (natural width, no wrapping)."""
    gutter = max((cell_len(lane.bc_name) for lane in flow.lanes), default=0)
    bc_color = _bc_colors(flow)

    out = Text(no_wrap=True, overflow="ignore")
    if flow.title:
        out.append("flow: ", style=_TITLE_STYLE)
        out.append(flow.title + "\n\n", style=_TITLE_STYLE)

    for i, lane in enumerate(flow.lanes):
        if i:
            out.append("\n")
        _append_lane(out, lane, gutter, bc_color[lane.bc_name])
    return out


def _bc_colors(flow: Flow) -> dict[str, str]:
    """Assign each unique bounded-context name a cycled lane colour."""
    colors: dict[str, str] = {}
    for lane in flow.lanes:
        if lane.bc_name not in colors:
            colors[lane.bc_name] = LANE_COLORS[len(colors) % len(LANE_COLORS)]
    return colors


def _append_lane(out: Text, lane: Lane, gutter: int, color: str) -> None:
    # Header: `<bcname padded> │ <description>`
    out.append(_pad(lane.bc_name, gutter), style=f"bold {color}")
    out.append(" │ ", style=_GUTTER_SEP_STYLE)
    out.append(lane.description + "\n")

    rows = _lane_band(lane)
    width = max((cell_len(r.plain) for r in rows), default=0)

    # Separator: `────┼────` with the ┼ under the header's │.
    sep = Text()
    sep.append("─" * (gutter + 1), style=_GUTTER_SEP_STYLE)
    sep.append("┼", style=_GUTTER_SEP_STYLE)
    sep.append("─" * (width + 1), style=_GUTTER_SEP_STYLE)
    out.append_text(sep)
    out.append("\n")

    prefix = " " * gutter + " │ "
    for r, row in enumerate(rows):
        out.append(prefix, style=_GUTTER_SEP_STYLE)
        out.append_text(row)
        if r < len(rows) - 1:
            out.append("\n")


def _lane_band(lane: Lane) -> list[Text]:
    """The three stacked rows (top/mid/bottom) of a lane's note boxes + arrows."""
    rows = [Text(), Text(), Text()]
    if not lane.notes:
        return rows
    for idx, note in enumerate(lane.notes):
        if idx:
            for r, seg in enumerate(_connector()):
                rows[r].append_text(seg)
        for r, seg in enumerate(_box(note)):
            rows[r].append_text(seg)
    _append_lane_end(rows, lane)
    return rows


def _connector() -> list[Text]:
    """A synchronous (`>`) arrow between two boxes, as top/mid/bottom rows."""
    return [Text("    "), Text(f" {SYNC_ARROW} "), Text("    ")]


def _append_lane_end(rows: list[Text], lane: Lane) -> None:
    """Trail the Join mark or async arrow after a lane's last box, if any."""
    if lane.joins_into_next:
        mark, style = JOIN_MARK, _JOIN_STYLE
    elif lane.notes and lane.notes[-1].is_async:
        mark, style = ASYNC_ARROW, _ASYNC_STYLE
    else:
        return
    pad = " " * (cell_len(mark) + 1)
    rows[0].append(pad)
    rows[1].append(" ")
    rows[1].append(mark, style=style)
    rows[2].append(pad)


def _box(note: Note) -> list[Text]:
    """One sticky note as three equal-width rows (top border / label / bottom)."""
    style = KIND_STYLE.get(note.kind, "white")
    kind = KIND_LABEL[note.kind]
    inner = min(max(cell_len(kind), cell_len(note.label), _MIN_INNER), _MAX_INNER)
    label = _truncate(note.label, inner)

    # Reserve the fan-out badge width on every row so the three stay aligned.
    badge_w = cell_len(FANOUT_BADGE) if note.is_fanout else 0

    top = Text()
    top.append("┌" + kind + "─" * (inner - cell_len(kind)) + "┐", style=style)
    if note.is_fanout:
        top.append(FANOUT_BADGE, style=style)

    mid = Text()
    mid.append("│" + label + " " * (inner - cell_len(label)) + "│", style=style)
    mid.append(" " * badge_w)

    bot = Text()
    bot.append("└" + "─" * inner + "┘", style=style)
    bot.append(" " * badge_w)
    return [top, mid, bot]


def _pad(s: str, width: int) -> str:
    """Right-pad *s* with spaces to *width* display cells (CJK-aware)."""
    return s + " " * max(0, width - cell_len(s))


def _truncate(s: str, width: int) -> str:
    """Truncate *s* to *width* display cells, appending '…' if it was cut."""
    if cell_len(s) <= width:
        return s
    out = ""
    for ch in s:
        if cell_len(out + ch) > width - 1:
            break
        out += ch
    return out + "…"


def flow_plain_text(flow: Flow) -> str:
    """The selectable / Ask-AI text for a flow — not used (the widget keeps the
    original DSL source instead), but provided for parity with diffview."""
    return render_flow(flow).plain
