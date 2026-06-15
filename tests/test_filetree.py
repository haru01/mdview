from pathlib import Path

from mdview.filetree import VIEWABLE_SUFFIXES, initial_file, is_viewable


def test_is_viewable_accepts_markdown_and_diff():
    assert is_viewable(Path("a.md"))
    assert is_viewable(Path("a.markdown"))
    assert is_viewable(Path("a.diff"))
    assert is_viewable(Path("a.patch"))


def test_is_viewable_is_case_insensitive():
    assert is_viewable(Path("README.MD"))


def test_is_viewable_rejects_other_files():
    assert not is_viewable(Path("a.txt"))
    assert not is_viewable(Path("a.py"))


def test_initial_file_prefers_readme(tmp_path):
    (tmp_path / "alpha.md").write_text("a")
    (tmp_path / "README.md").write_text("r")
    assert initial_file(tmp_path) == tmp_path / "README.md"


def test_initial_file_falls_back_to_first_sorted_markdown(tmp_path):
    (tmp_path / "beta.md").write_text("b")
    (tmp_path / "alpha.md").write_text("a")
    assert initial_file(tmp_path) == tmp_path / "alpha.md"


def test_initial_file_none_when_no_markdown(tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    assert initial_file(tmp_path) is None
