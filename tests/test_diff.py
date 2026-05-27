from __future__ import annotations

from mdview.diff import diff_to_markdown, looks_like_diff, parse_diff, parse_hunk_lines

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


# --- looks_like_diff (unchanged detection) ----------------------------------


def test_looks_like_diff_git_header() -> None:
    assert looks_like_diff(_BASIC)


def test_looks_like_diff_plain_unified() -> None:
    plain = "--- a/file.txt\n+++ b/file.txt\n@@ -1,2 +1,2 @@\n-old\n+new\n"
    assert looks_like_diff(plain)


def test_looks_like_diff_false_for_markdown() -> None:
    md = "# Title\n\nSome *markdown* with a - bullet and a +1 note.\n"
    assert not looks_like_diff(md)


def test_markdown_embedding_a_diff_example_is_not_detected() -> None:
    # A doc *about* diffs (diff inside a ```diff fence) must not be detected.
    doc = (
        "# How diffs work\n\nExample:\n\n"
        "```diff\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n```\n\nThe end.\n"
    )
    assert not looks_like_diff(doc)


# --- parse_diff: structure ---------------------------------------------------


def test_parse_diff_basic_structure() -> None:
    files = parse_diff(_BASIC)
    assert len(files) == 1
    f = files[0]
    assert f.path == "src/app.py"
    assert f.status == ""
    assert len(f.hunks) == 1
    h = f.hunks[0]
    assert h.header == "@@ -1,4 +1,4 @@ def main():"
    assert h.old_start == 1
    assert h.new_start == 1


def test_parse_diff_classifies_lines_and_numbers() -> None:
    h = parse_diff(_BASIC)[0].hunks[0]
    got = [(ln.kind, ln.old_no, ln.new_no, ln.text) for ln in h.lines]
    assert got == [
        ("context", 1, 1, "  import os"),
        ("del", 2, None, '  print("old")'),
        ("add", None, 2, '  print("new")'),
        ("context", 3, 3, "  return 0"),
    ]


def test_parse_diff_raw_is_a_valid_unified_hunk() -> None:
    # raw feeds text selection / Ask AI, so it must stay a valid unified diff:
    # the @@ header followed by the +/- body, markers intact, no line numbers.
    h = parse_diff(_BASIC)[0].hunks[0]
    assert h.raw == (
        "@@ -1,4 +1,4 @@ def main():\n"
        "   import os\n"
        '-  print("old")\n'
        '+  print("new")\n'
        "   return 0"
    )


def test_parse_diff_new_file_status() -> None:
    diff = (
        "diff --git a/new.txt b/new.txt\n"
        "new file mode 100644\n"
        "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,2 @@\n+line1\n+line2\n"
    )
    f = parse_diff(diff)[0]
    assert f.path == "new.txt"
    assert f.status == "new file"


def test_parse_diff_deleted_file_status() -> None:
    diff = (
        "diff --git a/old.txt b/old.txt\n"
        "deleted file mode 100644\n"
        "--- a/old.txt\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-line1\n-line2\n"
    )
    f = parse_diff(diff)[0]
    assert f.path == "old.txt"
    assert f.status == "deleted"


def test_parse_diff_rename_without_hunks() -> None:
    diff = (
        "diff --git a/oldname.py b/renamed.py\n"
        "similarity index 100%\nrename from oldname.py\nrename to renamed.py\n"
    )
    f = parse_diff(diff)[0]
    assert f.path == "renamed.py"
    assert f.status == "renamed"
    assert f.hunks == []


def test_parse_diff_binary_note() -> None:
    diff = (
        "diff --git a/img.png b/img.png\n"
        "index 1111111..2222222 100644\n"
        "Binary files a/img.png and b/img.png differ\n"
    )
    f = parse_diff(diff)[0]
    assert f.path == "img.png"
    assert "Binary files" in f.binary_note


def test_parse_diff_multiple_files_and_hunks() -> None:
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+A\n"
        "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n"
        "@@ -1 +1 @@\n-b\n+B\n@@ -5 +5 @@\n-c\n+C\n"
    )
    files = parse_diff(diff)
    assert [f.path for f in files] == ["a.py", "b.py"]
    assert [len(f.hunks) for f in files] == [1, 2]
    # second hunk of b.py is numbered from its own @@ start (5)
    assert files[1].hunks[1].old_start == 5


def test_parse_diff_plain_unified_without_git_header() -> None:
    plain = (
        "--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n-a\n+b\n c\n"
        "--- a/g.txt\n+++ b/g.txt\n@@ -1 +1 @@\n-x\n+y\n"
    )
    files = parse_diff(plain)
    assert [f.path for f in files] == ["f.txt", "g.txt"]


def test_parse_diff_crlf() -> None:
    diff = "diff --git a/x b/x\r\n--- a/x\r\n+++ b/x\r\n@@ -1 +1 @@\r\n-a\r\n+b\r\n"
    f = parse_diff(diff)[0]
    assert f.path == "x"
    assert "\r" not in f.hunks[0].raw


def test_parse_diff_form_feed_in_body_survives() -> None:
    diff = "diff --git a/c.py b/c.py\n--- a/c.py\n+++ b/c.py\n@@ -1 +1 @@\n+foo\x0cbar\n"
    line = parse_diff(diff)[0].hunks[0].lines[0]
    assert line.kind == "add"
    assert line.text == "foo\x0cbar"


# --- diff_to_markdown: headings kept, @@ no longer a heading -----------------


def test_diff_to_markdown_keeps_file_heading_drops_hunk_heading() -> None:
    out = diff_to_markdown(parse_diff(_BASIC))
    # `@ ` prefix is the `/` search hook (see diff_to_markdown / mdview.search)
    assert "## @ src/app.py" in out
    # @@ is NOT promoted to a heading any more
    assert "### " not in out
    # the hunk body lives in a diff fence (the placeholder the TUI swaps out)
    assert "```diff" in out
    assert '-  print("old")' in out
    assert '+  print("new")' in out
    # the git/index noise lines are dropped
    assert "index 1111111" not in out
    assert "diff --git" not in out


def test_diff_to_markdown_status_suffixes() -> None:
    new_diff = (
        "diff --git a/new.txt b/new.txt\nnew file mode 100644\n"
        "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+x\n"
    )
    assert "## @ new.txt (new file)" in diff_to_markdown(parse_diff(new_diff))


def test_diff_to_markdown_fence_length_escapes_embedded_backticks() -> None:
    diff = (
        "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n"
        "@@ -1,3 +1,3 @@\n text before\n-```\n+```python\n text after\n"
    )
    out = diff_to_markdown(parse_diff(diff))
    assert "````diff" in out


def test_diff_to_markdown_dunder_path_is_escaped() -> None:
    diff = (
        "diff --git a/pkg/__init__.py b/pkg/__init__.py\n"
        "--- a/pkg/__init__.py\n+++ b/pkg/__init__.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    )
    out = diff_to_markdown(parse_diff(diff))
    assert r"\_\_init\_\_" in out


# --- parse_hunk_lines: standalone fence bodies (README examples) -------------


def test_parse_hunk_lines_with_header() -> None:
    code = "@@ -1,2 +1,2 @@\n-old\n+new\n"
    h = parse_hunk_lines(code)
    assert h.old_start == 1
    assert [ln.kind for ln in h.lines] == ["del", "add"]


def test_parse_hunk_lines_without_header() -> None:
    code = "-old\n+new\n unchanged\n"
    h = parse_hunk_lines(code)
    assert h.header == ""
    assert [ln.kind for ln in h.lines] == ["del", "add", "context"]


# --- non-TTY rendering + CLI wiring -----------------------------------------


def test_print_diff_renders_delta_without_hunk_headings(capsys) -> None:
    from mdview.render import print_diff

    print_diff(parse_diff(_BASIC))
    out = capsys.readouterr().out
    assert "src/app.py" in out  # file banner
    assert "import os" in out  # code
    assert 'print("new")' in out
    assert "### " not in out  # @@ is never a markdown heading


def test_cli_detects_diff_file(tmp_path) -> None:
    from mdview.cli import _diff_files_for_path

    path = tmp_path / "change.diff"
    path.write_text(_BASIC, encoding="utf-8")
    files = _diff_files_for_path(path)
    assert files is not None
    assert files[0].path == "src/app.py"


def test_cli_passes_through_markdown_file(tmp_path) -> None:
    from mdview.cli import _diff_files_for_path

    path = tmp_path / "doc.md"
    path.write_text("# Title\n\nbody\n", encoding="utf-8")
    assert _diff_files_for_path(path) is None
