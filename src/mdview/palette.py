"""Colour palette for mdview's Obsidian-flavoured theme.

Single source of truth for the hex values used by the *runtime-built* `Content`
styles — search highlighting, `[[wikilinks]]`, the frontmatter panel, the fuzzy
pickers, the diff renderer, the event-flow title. The *declarative* side
(backgrounds, headings, emphasis, borders) lives in ``theme.css``; keep the two
in sync — the values here mirror the ``$accent`` / ``$rule`` / ``$text`` /
``$text-muted`` used there.

Design: Obsidian's default look is a near-monochrome greyscale (dark: ``#1e1e1e``
background, ``#dadada`` body) lifted by a single purple accent. There is no
second accent — bold/italic carry the body colour, and only links, tags, and
inline code wear the purple.
"""

from __future__ import annotations

# The purple accent (Obsidian dark ``--text-accent``): links, wikilinks, tags,
# inline code, the blockquote bar, modal borders, the command-line prompt.
ACCENT = "#7f6df2"

# A brighter accent for fuzzy-match highlighting inside the pickers, so the
# matched characters pop against a row that is otherwise body-coloured.
ACCENT_BRIGHT = "#9d8df5"

# Body foreground / muted grey (Obsidian ``--color-base-100`` / ``--color-base-60``).
TEXT = "#dadada"
TEXT_MUTED = "#999999"

# A dim grey for a broken ``[[wikilink]]`` (no such note in the tree yet), so a
# missing target reads as "not created" rather than as an accent link.
BROKEN_LINK = "#6e6e6e"

# `/` search highlighting: a dim purple wash for the whole match set, a brighter
# one for the current match (where n/N landed). Functional, but tied to the
# accent hue so the search reads as part of the same palette.
SEARCH_MATCH_BG = "#302b52"
SEARCH_CURRENT_BG = "#4c3fa8"

# Diff line backgrounds stay semantically green/red (unchanged); only the
# per-file heading rule follows the accent instead of the old cyan.
DIFF_ADD_BG = "#16331f"
DIFF_DEL_BG = "#3a1d1d"
DIFF_FILE_RULE = ACCENT
