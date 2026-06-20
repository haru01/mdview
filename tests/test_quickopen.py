from pathlib import Path

from mdview.quickopen import (
    DIFF_SOURCES,
    DiffSource,
    QuickOpenEntry,
    build_entries,
    fuzzy_filter,
    fuzzy_match,
    is_git_repo,
    list_viewable_files,
)


# --- list_viewable_files ---------------------------------------------------


def test_list_viewable_files_recurses_and_returns_relative_posix(tmp_path):
    (tmp_path / "README.md").write_text("r")
    sub = tmp_path / "docs"
    sub.mkdir()
    (sub / "guide.md").write_text("g")
    (tmp_path / "notes.txt").write_text("n")  # not viewable

    result = list_viewable_files(tmp_path)

    assert [p.as_posix() for p in result] == ["README.md", "docs/guide.md"]


def test_list_viewable_files_prunes_ignored_and_hidden_dirs(tmp_path):
    (tmp_path / "keep.md").write_text("k")
    for ignored in (".git", "node_modules", ".hidden"):
        d = tmp_path / ignored
        d.mkdir()
        (d / "buried.md").write_text("x")

    result = [p.as_posix() for p in list_viewable_files(tmp_path)]

    assert result == ["keep.md"]


def test_list_viewable_files_includes_diffs(tmp_path):
    (tmp_path / "a.diff").write_text("d")
    (tmp_path / "b.patch").write_text("p")
    (tmp_path / "c.md").write_text("m")

    result = [p.as_posix() for p in list_viewable_files(tmp_path)]

    assert result == ["a.diff", "b.patch", "c.md"]


# --- fuzzy_match -----------------------------------------------------------


def test_fuzzy_match_matches_subsequence():
    assert fuzzy_match("rdme", "README.md") is not None


def test_fuzzy_match_is_case_insensitive():
    assert fuzzy_match("RDM", "readme.md") is not None


def test_fuzzy_match_returns_none_when_chars_missing():
    assert fuzzy_match("xyz", "README.md") is None


def test_fuzzy_match_returns_matched_indices():
    score, indices = fuzzy_match("rd", "readme")
    # 'r' at 0, 'd' at 3
    assert indices == [0, 3]


def test_fuzzy_match_prefers_contiguous_over_gappy():
    contiguous = fuzzy_match("ab", "abxxxx")[0]
    gappy = fuzzy_match("ab", "axxxxb")[0]
    assert contiguous < gappy  # lower score is better


def test_fuzzy_match_prefers_start_of_path_segment():
    after_slash = fuzzy_match("g", "docs/guide.md")[0]
    mid_word = fuzzy_match("g", "imaging.md")[0]
    assert after_slash < mid_word


def test_fuzzy_match_empty_query_matches_with_no_indices():
    score, indices = fuzzy_match("", "anything.md")
    assert indices == []


# --- fuzzy_filter ----------------------------------------------------------


def test_fuzzy_filter_empty_query_returns_all_in_order():
    items = ["b.md", "a.md", "c.md"]
    result = fuzzy_filter("", items)
    assert [item for item, _ in result] == ["b.md", "a.md", "c.md"]


def test_fuzzy_filter_drops_non_matches_and_ranks():
    items = ["readme.md", "docs/guide.md", "changelog.md"]
    result = fuzzy_filter("gui", items)
    # only "docs/guide.md" has g..u..i as a subsequence
    assert [item for item, _ in result] == ["docs/guide.md"]


def test_fuzzy_filter_is_stable_for_equal_scores():
    # Two identical basenames in different dirs score the same; original order kept.
    items = ["x/readme.md", "y/readme.md"]
    result = fuzzy_filter("readme", items)
    assert [item for item, _ in result] == ["x/readme.md", "y/readme.md"]


def test_fuzzy_filter_uses_key_for_non_strings():
    items = [Path("docs/guide.md"), Path("readme.md")]
    result = fuzzy_filter("rdme", items, key=lambda p: p.as_posix())
    assert [item for item, _ in result] == [Path("readme.md")]


# --- is_git_repo -----------------------------------------------------------


def test_is_git_repo_true_when_dot_git_present(tmp_path):
    (tmp_path / ".git").mkdir()
    assert is_git_repo(tmp_path)


def test_is_git_repo_walks_up_from_subdir(tmp_path):
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    assert is_git_repo(sub)


def test_is_git_repo_false_without_dot_git(tmp_path):
    assert not is_git_repo(tmp_path)


def test_is_git_repo_accepts_dot_git_file(tmp_path):
    # git worktrees / submodules use a `.git` *file*, not a dir.
    (tmp_path / ".git").write_text("gitdir: /elsewhere\n")
    assert is_git_repo(tmp_path)


# --- diff sources / build_entries -----------------------------------------


def test_diff_sources_cover_working_staged_pr():
    sources = {d.source for d in DIFF_SOURCES}
    assert sources == {"working", "staged", "pr"}


def test_build_entries_lists_files_only_without_diffs():
    root = Path("/repo")
    files = [Path("a.md"), Path("docs/b.md")]
    entries = build_entries(root, files, include_diffs=False)
    assert all(isinstance(e, QuickOpenEntry) for e in entries)
    assert [e.label for e in entries] == ["a.md", "docs/b.md"]
    # file payloads are absolute paths under root
    assert entries[0].payload == root / "a.md"


def test_build_entries_prepends_diff_sources_when_included():
    root = Path("/repo")
    files = [Path("a.md")]
    entries = build_entries(root, files, include_diffs=True)
    # diff sources come first, each carrying a DiffSource payload
    assert isinstance(entries[0].payload, DiffSource)
    labels = [e.label for e in entries]
    assert "git diff" in labels
    assert labels[-1] == "a.md"  # files after the diff sources
