from __future__ import annotations

from mdview.diff import parse_diff

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
