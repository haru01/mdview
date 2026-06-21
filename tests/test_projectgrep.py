from __future__ import annotations

from pathlib import Path

from mdview.projectgrep import GrepHit, grep_files


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_grep_finds_matches_across_files_with_line_and_spans(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "hello world\nnothing here\nsay hello again\n")
    _write(tmp_path, "sub/b.md", "# title\nHELLO from sub\n")

    hits, truncated = grep_files(tmp_path, "hello")

    assert not truncated
    # Three matches: a.md line 1 and line 3, b.md line 2 (case-insensitive).
    by_rel = {(h.rel, h.line_no) for h in hits}
    assert ("a.md", 1) in by_rel
    assert ("a.md", 3) in by_rel
    assert ("sub/b.md", 2) in by_rel
    assert len(hits) == 3

    first = next(h for h in hits if h.rel == "a.md" and h.line_no == 1)
    assert first.line == "hello world"
    assert first.spans == [(0, 5)]
    assert first.path == tmp_path / "a.md"


def test_grep_is_case_insensitive_and_records_each_span(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "Foo foo FOO\n")
    hits, _ = grep_files(tmp_path, "foo")
    assert len(hits) == 1  # one line, but...
    assert hits[0].spans == [(0, 3), (4, 7), (8, 11)]  # ...three matched spans


def test_grep_empty_query_returns_no_hits(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "hello\n")
    hits, truncated = grep_files(tmp_path, "")
    assert hits == []
    assert not truncated


def test_grep_skips_non_viewable_files(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "needle\n")
    _write(tmp_path, "notes.txt", "needle\n")  # .txt is not viewable
    _write(tmp_path, "code.py", "needle\n")
    hits, _ = grep_files(tmp_path, "needle")
    assert {h.rel for h in hits} == {"a.md"}


def test_grep_searches_diff_files(tmp_path: Path) -> None:
    _write(tmp_path, "change.diff", "@@ -1 +1 @@\n-old\n+new TARGET line\n")
    hits, _ = grep_files(tmp_path, "TARGET")
    assert any(h.rel == "change.diff" for h in hits)


def test_grep_truncates_at_max_hits(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "\n".join("match" for _ in range(50)) + "\n")
    hits, truncated = grep_files(tmp_path, "match", max_hits=10)
    assert len(hits) == 10
    assert truncated


def test_grep_invalid_regex_falls_back_to_literal(tmp_path: Path) -> None:
    # A stray paren isn't valid regex; it must match literally, not raise.
    _write(tmp_path, "a.md", "call foo( now\n")
    hits, _ = grep_files(tmp_path, "foo(")
    assert len(hits) == 1
    assert hits[0].rel == "a.md"


def test_grep_supports_regex_queries(tmp_path: Path) -> None:
    _write(tmp_path, "a.md", "v1.2.3 release\nv9 draft\n")
    hits, _ = grep_files(tmp_path, r"v\d+\.\d+")
    assert {h.line_no for h in hits} == {1}


def test_grephit_is_a_dataclass() -> None:
    hit = GrepHit(path=Path("/x/a.md"), rel="a.md", line_no=1, line="x", spans=[(0, 1)])
    assert hit.line_no == 1
