"""Splice an in-memory edit into the document buffer (pure, no Textual).

The AI edit loop replaces a *line range* of the document source with new text:
the app derives the range from the selected blocks' ``source_range``s via
`selection_block_range`. Keeping the splice framework-free makes it directly
unit-testable, and is where the line/newline bookkeeping lives.
"""

from __future__ import annotations


def replace_line_range(document: str, start: int, end: int, replacement: str) -> str:
    """Return *document* with source lines ``[start, end)`` replaced by *replacement*.

    ``start``/``end`` index ``document.splitlines(keepends=True)`` (the same basis
    as a block's ``source_range``). Claude's reply is stripped of trailing
    newlines upstream, so the trailing-newline *run* of the removed span (the
    blank line that separates sections) is re-applied to the replacement — keeping
    the following block on its own line and preserving the visual separation.
    """
    lines = document.splitlines(keepends=True)
    before = "".join(lines[:start])
    after = "".join(lines[end:])
    removed = "".join(lines[start:end])
    trailing = removed[len(removed.rstrip("\n")) :]  # the removed span's trailing "\n" run
    if not trailing and after:
        trailing = "\n"  # ensure the next block isn't pulled onto the edited line
    body = replacement.rstrip("\n") + trailing
    return before + body + after


def selection_block_range(
    ranges: list[tuple[int, int]], document: str
) -> tuple[int, int] | None:
    """Merge selected blocks' ``source_range``s into one contiguous line range.

    *ranges* is each selected atomic block's ``(start_line, end_line)``. Returns
    the spanning ``(min_start, max_end)`` only when the blocks form one contiguous
    region — gaps between them must contain blank lines only (the blank line
    separating two selected paragraphs is fine; skipped real content is not).
    Returns None for an empty selection or a non-contiguous one (which can't be
    replaced as a single slice).
    """
    if not ranges:
        return None
    lines = document.splitlines(keepends=True)
    ordered = sorted(ranges)
    start, end = ordered[0]
    for nxt_start, nxt_end in ordered[1:]:
        if any(lines[i].strip() for i in range(end, min(nxt_start, len(lines)))):
            return None  # real (non-blank) content between blocks → not one slice
        end = max(end, nxt_end)
    return (start, end)
