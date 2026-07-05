"""Pure helpers for the LLM-wiki features (frontmatter, ``[[wikilinks]]``, tags).

Framework-free so it can be unit-tested without a TUI (the Textual wiring lives
in ``app.py`` and ``wiki_tag.py``). Three concerns:

- ``split_frontmatter`` — peel a leading ``---…---`` YAML block off a document.
  The prefix is kept *separate* from the body so the app can render the body
  (keeping ``document.source`` == the file minus its frontmatter, so the edit
  loop / dirty tracking stay intact) and reconstruct the original on ``:w`` by
  concatenating ``raw_prefix + body``.
- ``parse_wikilinks`` — find ``[[target#anchor|alias]]`` spans in text so the
  app can swap them for clickable links after rendering (source untouched).
- ``WikiIndex`` — a basename→paths and tag→paths map over a wiki tree, so a
  ``[[name]]`` resolves to a file anywhere in the tree and a tag lists the
  files that carry it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from mdview.quickopen import list_viewable_files

# A frontmatter block: ``---`` on the very first line, YAML, then a closing
# ``---`` line. DOTALL so the body spans newlines; anchored at the start so only
# a *leading* block counts (a ``---`` mid-document is a thematic break, not
# frontmatter). Both delimiter lines and the trailing newline are captured so
# ``raw_prefix`` round-trips.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?\r?\n)?---[ \t]*\r?\n", re.DOTALL)

# ``[[target#anchor|alias]]`` — ``#anchor`` and ``|alias`` optional. ``target``
# stops at ``#``/``|``/``]``; anchor stops at ``|``/``]``; alias is the rest.
_WIKILINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")


@dataclass(frozen=True)
class FrontmatterSplit:
    """The result of peeling frontmatter off a document.

    ``raw_prefix`` is the exact leading ``---…---\\n`` text (delimiters
    included) or ``None`` when there is no frontmatter; ``meta`` is the parsed
    mapping (empty when none / unparseable); ``body`` is the remainder.
    ``(raw_prefix or "") + body`` always reconstructs the original text.
    """

    raw_prefix: str | None
    meta: dict
    body: str


@dataclass(frozen=True)
class WikiLink:
    """One ``[[…]]`` occurrence. ``start``/``end`` are offsets into the source
    text (``text[start:end]`` is the whole ``[[…]]``); ``alias`` defaults to
    ``target`` and ``anchor`` is ``""`` when absent."""

    start: int
    end: int
    target: str
    anchor: str
    alias: str


def split_frontmatter(text: str) -> FrontmatterSplit:
    """Peel a leading YAML frontmatter block off *text*.

    No frontmatter (or a block with no closing ``---``) is returned as-is
    (``raw_prefix=None``, ``meta={}``, ``body=text``) — idempotent. A block that
    parses to something other than a mapping (or fails to parse) yields an empty
    ``meta`` but still strips the prefix, so the raw YAML never renders.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return FrontmatterSplit(raw_prefix=None, meta={}, body=text)
    raw_prefix = match.group(0)
    yaml_text = match.group(1) or ""
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        parsed = None
    meta = parsed if isinstance(parsed, dict) else {}
    return FrontmatterSplit(raw_prefix=raw_prefix, meta=meta, body=text[match.end():])


def parse_wikilinks(text: str) -> list[WikiLink]:
    """Every ``[[target#anchor|alias]]`` in *text*, in order of appearance."""
    links: list[WikiLink] = []
    for m in _WIKILINK_RE.finditer(text):
        target = m.group(1).strip()
        anchor = (m.group(2) or "").strip()
        alias = (m.group(3) or "").strip() or target
        links.append(
            WikiLink(
                start=m.start(),
                end=m.end(),
                target=target,
                anchor=anchor,
                alias=alias,
            )
        )
    return links


@dataclass(frozen=True)
class FrontmatterDisplay:
    """A frontmatter mapping arranged for the panel.

    ``title`` is rendered as the panel heading; ``tags`` become clickable
    chips (→ tag search) and ``sources`` clickable wiki links (each is a source
    path's stem); ``meta_line`` is the remaining scalar fields joined with
    ``·`` in frontmatter order (``title``/``tags``/``sources`` excluded).
    """

    title: str | None
    tags: list[str]
    sources: list[str]
    meta_line: str


def _as_str_list(raw) -> list[str]:
    """Normalise a frontmatter value that may be a scalar or a list to a list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [str(raw)]


def frontmatter_display(meta: dict) -> FrontmatterDisplay:
    """Arrange a parsed frontmatter *meta* mapping for panel rendering."""
    title = meta.get("title")
    tags = _tags_of(meta)
    sources = [Path(str(s)).stem for s in _as_str_list(meta.get("sources"))]
    special = {"title", "tags", "sources"}
    parts = [
        f"{key}: {value}"
        for key, value in meta.items()
        if key not in special and value is not None
    ]
    return FrontmatterDisplay(
        title=str(title) if title is not None else None,
        tags=tags,
        sources=sources,
        meta_line=" · ".join(parts),
    )


def _tags_of(meta: dict) -> list[str]:
    """The frontmatter ``tags`` as a list of strings (tolerating a scalar)."""
    raw = meta.get("tags")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(t) for t in raw]
    return []


@dataclass
class WikiIndex:
    """Basename→paths and tag→paths maps over a wiki tree.

    Built once per root (``build``); ``resolve`` maps a ``[[name]]`` to the
    file(s) whose stem is *name* (a list — empty = broken link, >1 = ambiguous),
    and ``files_with_tag`` lists the files carrying a frontmatter tag.
    """

    root: Path
    by_stem: dict[str, list[Path]] = field(default_factory=dict)
    by_tag: dict[str, list[Path]] = field(default_factory=dict)

    @classmethod
    def build(cls, root: Path) -> WikiIndex:
        root = Path(root)
        index = cls(root=root)
        for rel in list_viewable_files(root):
            path = root / rel
            index.by_stem.setdefault(path.stem, []).append(path)
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            meta = split_frontmatter(text).meta
            for tag in _tags_of(meta):
                index.by_tag.setdefault(tag, []).append(path)
        return index

    def resolve(self, name: str) -> list[Path]:
        """Files whose stem is *name* (order stable). Empty = broken link."""
        return list(self.by_stem.get(name.strip(), []))

    def files_with_tag(self, tag: str) -> list[Path]:
        """Files whose frontmatter ``tags`` include *tag* (order stable)."""
        return list(self.by_tag.get(tag, []))
