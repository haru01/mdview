"""Parse an EventStorming ``event-flow-svg`` fence into a flow model.

Pure and framework-free (no Textual): the model and parser here are unit-tested
directly, and the rendering lives in ``mdview.eventflowview`` / the Textual
wrapper in ``mdview.eventflow_widget`` — the project's usual pure/wrapper split.

The DSL is the one authored inside EventStorming Markdown documents (the
``pocket-modeling`` toolkit). A fence body looks like::

    title: ハッピーパス
    flow:
    |community|: 主催者が活動を始める
      @主催者 > !コミュニティを作成 > [コミュニティが作成された] >>
    |participation|: 自動承認 or 補欠
      $AutoApprove > !承認する > ?残席数 > [承認された]

Grammar (kept faithful to the toolkit's ``eventstorming_build.py``):

* ``title: …`` sets the flow title; ``flow:`` opens the flow section.
* ``|BCName|: description`` starts a lane (a swimlane row, one bounded context).
* Element prefixes: ``@`` actor, ``!`` command, ``$`` policy, ``?`` read model,
  ``[…]`` event; a bare word is a command.
* Operators, in precedence order: a trailing ``&>>`` is a Join + async transition
  (sets ``Lane.joins_into_next``); a trailing ``>>`` is a plain async transition
  (marks the last ``Note`` ``is_async``); ``*>`` splits a line into a fan-out
  (BULK) — every note after the first ``*>`` segment is ``is_fanout``; within a
  segment ``>`` separates synchronous notes.
* ``#``-led lines are comments.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Element prefix → note kind. ``[…]`` (event) and the bare-word fallback
# (command) are handled separately in ``parse_dsl_item``.
DSL_PREFIX_TO_KIND = {"@": "actor", "!": "command", "$": "policy", "?": "readmodel"}

# Display label shown on each note's top border (the EventStorming "kind").
KIND_LABEL = {
    "actor": "Actor",
    "command": "Command",
    "event": "Event",
    "policy": "Policy",
    "readmodel": "Read Model",
}


@dataclass
class Note:
    """One sticky note: an actor/command/event/policy/read-model."""

    kind: str  # actor | command | event | policy | readmodel
    label: str
    is_async: bool = False  # last note of a lane ending in `>>` (or `&>>`)
    is_fanout: bool = False  # note after a `*>` BULK fork (drawn stacked, ×N)


@dataclass
class Lane:
    """One swimlane row: a bounded context and its ordered notes."""

    bc_name: str
    description: str
    notes: list[Note] = field(default_factory=list)
    joins_into_next: bool = False  # trailing `&>>`: Join transition to next lane


@dataclass
class Flow:
    """A whole event flow: a title and its swimlane rows."""

    title: str
    lanes: list[Lane] = field(default_factory=list)


def parse_flow_dsl(dsl: str) -> Flow | None:
    """Parse a fence body into a :class:`Flow`, or ``None`` if it has no lanes."""
    flow = Flow(title="")
    current_lane: Lane | None = None

    for raw in dsl.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = re.match(r"^title:\s*(.+)$", line)
        if m:
            flow.title = m.group(1).strip()
            continue

        if line == "flow:":
            continue

        lane_match = re.match(r"^\|([^|]+)\|:\s*(.*)$", line)
        if lane_match:
            current_lane = Lane(
                bc_name=lane_match.group(1).strip(),
                description=lane_match.group(2).strip(),
            )
            flow.lanes.append(current_lane)
            continue

        if current_lane is None:
            continue

        notes, joins_into_next = parse_flow_line(line)
        current_lane.notes.extend(notes)
        if joins_into_next:
            # A trailing `&>>` on any line of the lane marks the lane's Join.
            current_lane.joins_into_next = True

    return flow if flow.lanes else None


def parse_flow_line(line: str) -> tuple[list[Note], bool]:
    """Parse one body line → ``(notes, joins_into_next)``.

    Operator precedence: a trailing ``&>>`` (Join + async) or ``>>`` (async) is
    stripped first and recorded; then ``*>`` splits fan-out segments (segments
    after the first are ``is_fanout``); within a segment ``>`` separates notes.
    """
    line = line.strip()
    if not line:
        return [], False

    joins_into_next = line.endswith("&>>")
    if joins_into_next:
        line = line[:-3].rstrip()
        has_async_end = True
    else:
        has_async_end = line.endswith(">>")
        if has_async_end:
            line = line[:-2].rstrip()

    notes: list[Note] = []
    for seg_idx, seg in enumerate(re.split(r"\*>", line)):
        in_fanout = seg_idx > 0
        for part in (p.strip() for p in seg.split(">")):
            note = parse_dsl_item(part)
            if note:
                note.is_fanout = in_fanout
                notes.append(note)
    if notes and has_async_end:
        notes[-1].is_async = True
    return notes, joins_into_next


def parse_dsl_item(item: str) -> Note | None:
    """Parse a single token (``@x``/``!x``/``[x]``/``$x``/``?x``/bare) → Note."""
    item = item.strip()
    if not item:
        return None
    if item.startswith("[") and item.endswith("]"):
        return Note(kind="event", label=item[1:-1].strip())
    if item[0] in DSL_PREFIX_TO_KIND:
        return Note(kind=DSL_PREFIX_TO_KIND[item[0]], label=item[1:].strip())
    return Note(kind="command", label=item)
