from __future__ import annotations

from mdview.diff import diff_to_markdown, looks_like_diff, maybe_diff_to_markdown

_BASIC = (
    "diff --git a/src/app.py b/src/app.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/src/app.py\n"
    "+++ b/src/app.py\n"
    "@@ -1,4 +1,4 @@ def main():\n"
    "   import os\n"
    '-  print("old")\n'
    '+  print("new")\n'
    "   return 0\n"
)


def test_looks_like_diff_git_header() -> None:
    assert looks_like_diff(_BASIC)


def test_looks_like_diff_plain_unified() -> None:
    plain = (
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -1,2 +1,2 @@\n"
        "-old\n"
        "+new\n"
    )
    assert looks_like_diff(plain)


def test_looks_like_diff_false_for_markdown() -> None:
    md = "# Title\n\nSome *markdown* with a - bullet and a +1 note.\n"
    assert not looks_like_diff(md)


def test_basic_diff_becomes_file_and_hunk_headings() -> None:
    out = diff_to_markdown(_BASIC)
    assert "## src/app.py" in out
    assert "### @@ -1,4 +1,4 @@ def main():" in out
    # the +/- lines survive inside a diff fence so pygments can colour them
    assert "```diff" in out
    assert '-  print("old")' in out
    assert '+  print("new")' in out
    # the git/index/--- /+++ noise lines are dropped
    assert "index 1111111" not in out
    assert "diff --git" not in out


def test_new_file_marked() -> None:
    diff = (
        "diff --git a/new.txt b/new.txt\n"
        "new file mode 100644\n"
        "index 0000000..abcdef0\n"
        "--- /dev/null\n"
        "+++ b/new.txt\n"
        "@@ -0,0 +1,2 @@\n"
        "+line1\n"
        "+line2\n"
    )
    out = diff_to_markdown(diff)
    assert "## new.txt (new file)" in out


def test_deleted_file_marked() -> None:
    diff = (
        "diff --git a/old.txt b/old.txt\n"
        "deleted file mode 100644\n"
        "index abcdef0..0000000\n"
        "--- a/old.txt\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-line1\n"
        "-line2\n"
    )
    out = diff_to_markdown(diff)
    assert "## old.txt (deleted)" in out


def test_rename_without_content_change() -> None:
    diff = (
        "diff --git a/oldname.py b/renamed.py\n"
        "similarity index 100%\n"
        "rename from oldname.py\n"
        "rename to renamed.py\n"
    )
    out = diff_to_markdown(diff)
    assert "## renamed.py (renamed)" in out
    # no hunks → no diff fence
    assert "```diff" not in out


def test_binary_file_note() -> None:
    diff = (
        "diff --git a/img.png b/img.png\n"
        "index 1111111..2222222 100644\n"
        "Binary files a/img.png and b/img.png differ\n"
    )
    out = diff_to_markdown(diff)
    assert "## img.png" in out
    assert "Binary files" in out


def test_fence_length_escapes_embedded_backticks() -> None:
    # diff of a markdown file whose content contains a ``` code fence:
    # a context/added line of three backticks must NOT prematurely close ours.
    diff = (
        "diff --git a/README.md b/README.md\n"
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1,3 +1,3 @@\n"
        " text before\n"
        "-```\n"
        "+```python\n"
        " text after\n"
    )
    out = diff_to_markdown(diff)
    # opening fence must be at least 4 backticks to contain a 3-backtick line
    assert "````diff" in out


def test_dunder_path_is_escaped() -> None:
    diff = (
        "diff --git a/pkg/__init__.py b/pkg/__init__.py\n"
        "--- a/pkg/__init__.py\n"
        "+++ b/pkg/__init__.py\n"
        "@@ -1 +1 @@\n"
        "-x = 1\n"
        "+x = 2\n"
    )
    out = diff_to_markdown(diff)
    # underscores escaped so markdown doesn't bold "init"
    assert r"\_\_init\_\_" in out


def test_multiple_files_and_hunks() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+A\n"
        "diff --git a/b.py b/b.py\n"
        "--- a/b.py\n"
        "+++ b/b.py\n"
        "@@ -1 +1 @@\n"
        "-b\n"
        "+B\n"
        "@@ -5 +5 @@\n"
        "-c\n"
        "+C\n"
    )
    out = diff_to_markdown(diff)
    assert "## a.py" in out
    assert "## b.py" in out
    # two hunks in b.py
    assert out.count("### @@") == 3


def test_plain_diff_transforms_without_hanging() -> None:
    # A plain unified diff has no `diff --git` line; the parser must still make
    # forward progress (regression: this used to spin forever).
    plain = (
        "--- a/f.txt\n"
        "+++ b/f.txt\n"
        "@@ -1,2 +1,2 @@\n"
        "-a\n"
        "+b\n"
        " c\n"
        "--- a/g.txt\n"
        "+++ b/g.txt\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
    )
    out = diff_to_markdown(plain)
    assert "## f.txt" in out
    assert "## g.txt" in out
    assert out.count("### @@") == 2
    assert "-a" in out and "+b" in out


def test_form_feed_in_body_is_not_split() -> None:
    # str.splitlines() breaks on \x0c; that would strip the `+` prefix off the
    # tail fragment. The body line must survive intact.
    diff = (
        "diff --git a/c.py b/c.py\n"
        "--- a/c.py\n"
        "+++ b/c.py\n"
        "@@ -1 +1 @@\n"
        "+foo\x0cbar\n"
    )
    out = diff_to_markdown(diff)
    assert "+foo\x0cbar" in out
    # the fragment must not appear on its own line without a +/- prefix
    assert "\nbar\n" not in out


def test_crlf_diff_is_handled() -> None:
    diff = "diff --git a/x b/x\r\n--- a/x\r\n+++ b/x\r\n@@ -1 +1 @@\r\n-a\r\n+b\r\n"
    out = diff_to_markdown(diff)
    assert "## x" in out
    assert "-a" in out and "+b" in out
    assert "\r" not in out


def test_markdown_embedding_a_diff_example_is_not_detected() -> None:
    # A doc *about* diffs (diff inside a ```diff fence) must not be rewritten.
    doc = (
        "# How diffs work\n\n"
        "Example:\n\n"
        "```diff\n"
        "--- a/x\n"
        "+++ b/x\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "```\n\n"
        "The end.\n"
    )
    assert not looks_like_diff(doc)
    assert maybe_diff_to_markdown(doc) == doc


def test_maybe_passthrough_for_non_diff() -> None:
    md = "# Title\n\nbody\n"
    assert maybe_diff_to_markdown(md) == md


def test_maybe_transforms_diff() -> None:
    assert maybe_diff_to_markdown(_BASIC) != _BASIC
    assert "## src/app.py" in maybe_diff_to_markdown(_BASIC)


def test_cli_detects_diff_file(tmp_path) -> None:
    from pathlib import Path

    from mdview.cli import _diff_markdown_for_file

    path: Path = tmp_path / "change.diff"
    path.write_text(_BASIC, encoding="utf-8")
    md = _diff_markdown_for_file(path)
    assert md is not None
    assert "## src/app.py" in md


def test_cli_passes_through_markdown_file(tmp_path) -> None:
    from mdview.cli import _diff_markdown_for_file

    path = tmp_path / "doc.md"
    path.write_text("# Title\n\nbody\n", encoding="utf-8")
    assert _diff_markdown_for_file(path) is None
