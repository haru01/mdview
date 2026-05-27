"""Semantic selection: expand a selection along the Markdown structure.

Textual renders a Markdown document into a widget tree. This module turns a
single clicked widget into an *expansion ladder*: an ordered list of selection
"scopes" that grow from the smallest block up to the whole document, following
the document's structure (block → list item → list/quote → section → document).

The functions here are pure with respect to the widget tree — they only read
the tree and never mutate selection state. Applying a scope (setting
``Screen.selections``) is the caller's job; see ``MdViewerApp._apply_scope``.

Note on the mounted tree: Textual does **not** mount ``MarkdownListItem``
widgets. A list item is a ``Horizontal`` (bullet + ``Vertical`` of the item's
blocks) whose parent is a ``MarkdownList``. Tables are a single
``MarkdownTableContent`` widget, so a table is atomic (no cell/row widgets).
"""

from __future__ import annotations

from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets._markdown import (
    Markdown,
    MarkdownBlockQuote,
    MarkdownFence,
    MarkdownHeader,
    MarkdownHorizontalRule,
    MarkdownList,
    MarkdownParagraph,
    MarkdownTable,
)

from mdview.diff_widget import DiffHunk

# Smallest selectable "blocks" — widgets that render their own text.
ATOMIC_BLOCKS: tuple[type[Widget], ...] = (
    MarkdownHeader,
    MarkdownParagraph,
    MarkdownFence,
    MarkdownHorizontalRule,
    MarkdownTable,
    DiffHunk,  # delta-styled diff hunk (replaces a ```diff fence in the tree)
)

# Structural containers that form intermediate expansion rungs.
CONTAINER_BLOCKS: tuple[type[Widget], ...] = (
    MarkdownBlockQuote,
    MarkdownList,
)


def find_leaf_block(widget: Widget | None) -> Widget | None:
    """Resolve a clicked widget to the smallest enclosing Markdown block.

    Walks self → ancestors for an atomic block; failing that (e.g. a click on
    a list item's container padding), descends to the first atomic block inside
    the widget. Returns ``None`` for non-Markdown widgets such as images.
    """
    if widget is None:
        return None
    for node in widget.ancestors_with_self:
        if isinstance(node, ATOMIC_BLOCKS):
            return node
    # Descend only when the click landed strictly inside the document (e.g. on a
    # list item's container). A click on the document/screen background selects
    # nothing rather than snapping to the first block.
    if any(isinstance(ancestor, Markdown) for ancestor in widget.ancestors):
        for node in widget.query("*"):
            if isinstance(node, ATOMIC_BLOCKS):
                return node
    return None


def build_scopes(leaf: Widget, document: Markdown) -> list[list[Widget]]:
    """Build the expansion ladder for ``leaf`` within ``document``.

    Each rung is a list of *root* widgets; selecting a rung means selecting each
    root and all of its descendants. Rungs grow monotonically:

        block → (list item → list / blockquote …) → section → document

    Consecutive rungs that would select the same set of widgets are collapsed,
    so every click visibly grows the selection.
    """
    scopes: list[list[Widget]] = [[leaf]]

    for ancestor in leaf.ancestors:
        if ancestor is document:
            break
        if isinstance(ancestor, Horizontal) and isinstance(ancestor.parent, MarkdownList):
            scopes.append([ancestor])  # one list item (bullet + content)
        elif isinstance(ancestor, CONTAINER_BLOCKS):
            scopes.append([ancestor])  # whole list / blockquote

    scopes.extend(_section_rungs(leaf, document))

    scopes.append(list(document.children))  # whole document

    return _dedupe(scopes)


def _section_rungs(leaf: Widget, document: Markdown) -> list[list[Widget]]:
    """Heading-delimited sections enclosing ``leaf``, from innermost outward.

    Expansion follows the heading hierarchy so it grows gradually: the leaf's
    own section, then each enclosing (shallower-level) heading's section, up to
    the top. Each section runs from its heading to just before the next heading
    of equal or higher level, so it includes its subsections. Content before the
    first heading forms a single section of its own.
    """
    children = list(document.children)
    top = _top_level_block(leaf, document)
    if top not in children:
        return []
    index = children.index(top)

    heading_index: int | None = None
    for i in range(index, -1, -1):
        if isinstance(children[i], MarkdownHeader):
            heading_index = i
            break

    if heading_index is None:
        end = next(
            (j for j, c in enumerate(children) if isinstance(c, MarkdownHeader)),
            len(children),
        )
        return [children[:end]] if end else []

    rungs: list[list[Widget]] = []
    current = heading_index
    while current is not None:
        level = children[current].LEVEL
        rungs.append(children[current : _section_end(children, current, level)])
        current = next(
            (
                i
                for i in range(current - 1, -1, -1)
                if isinstance(children[i], MarkdownHeader) and children[i].LEVEL < level
            ),
            None,
        )
    return rungs


def _section_end(children: list[Widget], start: int, level: int) -> int:
    """Index just past a section that begins at ``start`` (a heading of ``level``)."""
    for j in range(start + 1, len(children)):
        child = children[j]
        if isinstance(child, MarkdownHeader) and child.LEVEL <= level:
            return j
    return len(children)


def _top_level_block(leaf: Widget, document: Markdown) -> Widget:
    """The ancestor-or-self of ``leaf`` whose parent is the document."""
    for node in leaf.ancestors_with_self:
        if node.parent is document:
            return node
    return leaf


def _dedupe(scopes: list[list[Widget]]) -> list[list[Widget]]:
    """Drop rungs whose selected-widget set repeats the previous rung's."""
    result: list[list[Widget]] = []
    previous: frozenset[Widget] | None = None
    for roots in scopes:
        widgets: set[Widget] = set()
        for root in roots:
            widgets.add(root)
            widgets.update(root.query("*"))
        key = frozenset(widgets)
        if key != previous:
            result.append(roots)
            previous = key
    return result
