from __future__ import annotations

from pathlib import Path

import pytest

from mdview.app import MdViewerApp, _paragraph_image_src

FIXTURES = Path(__file__).parent / "fixtures"


def test_sample_svg_paragraph_is_replaced_with_image_widget() -> None:
    """Smoke test: app launches, loads the sample, replaces a paragraph with an Image."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:  # noqa: D401

        app = MdViewerApp(md)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            from textual_image.widget import Image
            from textual.widgets._markdown import MarkdownParagraph

            # Image widget must have been injected from the SVG reference.
            images = list(app.query(Image))
            assert images, "expected at least one Image widget for sample.svg"

            # No remaining MarkdownParagraph should contain only the SVG image.
            for paragraph in app.query(MarkdownParagraph):
                assert _paragraph_image_src(paragraph) is None

    asyncio.run(driver())


def test_all_headings_render_in_claude_orange() -> None:
    """H1–H6 share a single orange hue (#d97757, Claude's mascot color)."""
    import asyncio

    from textual.widgets._markdown import (
        MarkdownH1,
        MarkdownH2,
        MarkdownH3,
        MarkdownH4,
        MarkdownH5,
        MarkdownH6,
    )

    md = FIXTURES / "sample.md"
    orange_rgb = (217, 119, 87)  # #d97757

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            for heading_cls in (
                MarkdownH1,
                MarkdownH2,
                MarkdownH3,
                MarkdownH4,
                MarkdownH5,
                MarkdownH6,
            ):
                widgets = list(app.query(heading_cls))
                assert widgets, f"sample should contain a {heading_cls.__name__}"
                color = widgets[0].styles.color
                assert (color.r, color.g, color.b) == orange_rgb, (
                    f"{heading_cls.__name__} should be orange, got {color}"
                )

    asyncio.run(driver())


def test_accent_palette_is_orange_and_green() -> None:
    """3-color scheme: orange marks structure (quote bar), green marks inline emphasis."""
    import asyncio

    from textual.widgets._markdown import (
        MarkdownBlockQuote,
        MarkdownHorizontalRule,
        MarkdownParagraph,
        MarkdownTableContent,
    )

    md = FIXTURES / "sample.md"
    orange = (217, 119, 87)  # #d97757
    green = (78, 191, 113)  # #4EBF71

    def rgb(color):  # noqa: ANN001, ANN202
        return (color.r, color.g, color.b)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()

            # Inline emphasis (bold / italic / inline code) is green so the body
            # text doesn't read as a wall of orange.
            para = app.query(MarkdownParagraph).first()
            assert rgb(para.get_component_styles("strong").color) == green
            assert rgb(para.get_component_styles("code_inline").color) == green
            assert rgb(para.get_component_styles("em").color) == green

            hr = app.query(MarkdownHorizontalRule).first()
            assert rgb(hr.styles.color) == green

            keyline = app.query(MarkdownTableContent).first().styles.keyline
            assert rgb(keyline[1]) == green

            border = app.query(MarkdownBlockQuote).first().styles.border_left
            assert rgb(border[1]) == orange

    asyncio.run(driver())


def test_n_and_p_navigate_between_headings() -> None:
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()

            from textual.widgets import MarkdownViewer

            viewer = app.query_one(MarkdownViewer)
            start = viewer.scroll_y

            await pilot.press("n")
            await pilot.pause()
            after_first_n = viewer.scroll_y
            assert after_first_n > start, "`n` should move scroll down to next heading"

            await pilot.press("n")
            await pilot.pause()
            after_second_n = viewer.scroll_y
            assert after_second_n > after_first_n, "`n` should advance further"

            await pilot.press("p")
            await pilot.pause()
            after_p = viewer.scroll_y
            assert after_p < after_second_n, "`p` should move back to previous heading"

    asyncio.run(driver())


def test_table_widget_is_rendered() -> None:
    """Sample has a markdown table; Textual must materialize it as MarkdownTable."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            from textual.widgets._markdown import MarkdownTable

            tables = list(app.query(MarkdownTable))
            assert tables, "expected at least one MarkdownTable widget"
            t = tables[0]
            assert [str(h) for h in t._headers] == ["Key", "Value"]
            assert len(t._rows) == 3

    asyncio.run(driver())


def test_anchor_link_scrolls_to_section() -> None:
    """`#mermaid` anchor click via LinkClicked must scroll the viewer."""
    import asyncio

    from textual.widgets import Markdown, MarkdownViewer

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            doc = viewer.document
            before = viewer.scroll_y
            doc.post_message(Markdown.LinkClicked(doc, "#mermaid"))
            await pilot.pause()
            await pilot.pause()
            assert viewer.scroll_y > before, "anchor click should scroll down"

    asyncio.run(driver())


def test_markdown_link_navigates_to_other_file() -> None:
    """Clicking `[..](other.md)` should load the other markdown file."""
    import asyncio

    from textual.widgets import Markdown, MarkdownViewer

    md = FIXTURES / "link_a.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            doc = viewer.document
            assert app._md_path.name == "link_a.md"

            doc.post_message(Markdown.LinkClicked(doc, "link_b.md"))
            for _ in range(10):
                await pilot.pause()
                if app._md_path.name == "link_b.md":
                    break
            assert app._md_path.name == "link_b.md"
            assert app.title == "link_b.md"

    asyncio.run(driver())


def test_markdown_link_with_anchor_jumps_to_section() -> None:
    """`other.md#anchor` loads file and jumps to anchor."""
    import asyncio

    from textual.widgets import Markdown, MarkdownViewer

    md = FIXTURES / "link_a.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            doc = viewer.document

            doc.post_message(Markdown.LinkClicked(doc, "link_b.md#section-two"))
            for _ in range(20):
                await pilot.pause()
                if app._md_path.name == "link_b.md" and viewer.scroll_y > 0:
                    break
            assert app._md_path.name == "link_b.md"
            # anchor jump should scroll past the top of the document
            assert viewer.scroll_y > 0

    asyncio.run(driver())


def test_back_returns_to_previous_file() -> None:
    """`b` keybinding pops history and reloads the prior file."""
    import asyncio

    from textual.widgets import Markdown, MarkdownViewer

    md = FIXTURES / "link_a.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            doc = viewer.document

            doc.post_message(Markdown.LinkClicked(doc, "link_b.md"))
            for _ in range(10):
                await pilot.pause()
                if app._md_path.name == "link_b.md":
                    break
            assert app._md_path.name == "link_b.md"

            await pilot.press("b")
            for _ in range(10):
                await pilot.pause()
                if app._md_path.name == "link_a.md":
                    break
            assert app._md_path.name == "link_a.md"

    asyncio.run(driver())


def test_stdin_content_loads_and_titles() -> None:
    """Content passed in (as from piped stdin) renders and titles as (stdin)."""
    import asyncio

    from textual.widgets import MarkdownViewer

    async def driver() -> None:
        app = MdViewerApp(content="# Piped\n\nHello from stdin.")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app.title == "(stdin)"
            assert app._md_dir == Path.cwd()
            viewer = app.query_one(MarkdownViewer)
            assert "Piped" in viewer.document.source

    asyncio.run(driver())


def test_stdin_base_dir_overrides_resolution_root(tmp_path: Path) -> None:
    """base_dir sets where relative images/links resolve for stdin content."""
    import asyncio

    async def driver() -> None:
        app = MdViewerApp(content="# x", base_dir=tmp_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app._md_dir == tmp_path.resolve()

    asyncio.run(driver())


def test_ask_ai_without_selection_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pressing `h` with no selection warns instead of opening the modal."""
    import asyncio

    from mdview.ask_ai import AskAiScreen

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert not isinstance(app.screen, AskAiScreen), "no selection should not open the modal"

    asyncio.run(driver())


def test_question_mark_toggles_help_and_h_does_not() -> None:
    """`?` opens the help panel; `h` is Ask AI now and must not open help."""
    import asyncio

    from textual.widgets import HelpPanel

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert app.screen.query(HelpPanel), "`?` should open the help panel"
            await pilot.press("question_mark")
            await pilot.pause()
            assert not app.screen.query(HelpPanel), "`?` should toggle the help panel off"
            # `h` (no selection) warns for Ask AI rather than opening help.
            await pilot.press("h")
            await pilot.pause()
            assert not app.screen.query(HelpPanel), "`h` should no longer open help"

    asyncio.run(driver())


def test_ask_ai_opens_modal_with_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With text selected and claude on PATH, `h` opens the AskAiScreen modal."""
    import asyncio
    import os

    from tests.test_ai import _fake_claude
    from mdview.ask_ai import AskAiScreen

    claude = _fake_claude(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    import shutil

    shutil.copy(claude, bindir / "claude")
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            # Simulate a selection by populating the screen's selection map via
            # select-all, which the framework supports.
            app.screen.text_select_all()
            await pilot.pause()
            assert app.screen.get_selected_text(), "select-all should yield text"
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen), "selection should open the modal"

            from textual.widgets import Checkbox, Input

            input_widget = app.screen.query_one("#ask-ai-input", Input)
            assert input_widget.value == "わかりやすく解説して", (
                "input should pre-fill a plain (non-SVG) default question"
            )

            # SVG diagramming is opt-in: the toggle starts unchecked.
            toggle = app.screen.query_one("#ask-ai-svg-toggle", Checkbox)
            assert toggle.value is False, "SVG mode should be off by default"

            # The popup is enlarged for research-style reading.
            dialog = app.screen.query_one("#ask-ai-dialog")
            assert dialog.styles.width.value == 90
            assert dialog.styles.height.value == 90

    asyncio.run(driver())


def test_ask_ai_toggling_svg_refocuses_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Toggling the SVG checkbox returns focus to the input, so Enter still sends
    the question instead of just flipping the checkbox again."""
    import asyncio

    from textual.widgets import Checkbox, Input

    from mdview.ask_ai import AskAiScreen

    _claude_on_path(tmp_path, monkeypatch, stdout="ok")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.screen.text_select_all()
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen)

            checkbox = app.screen.query_one("#ask-ai-svg-toggle", Checkbox)
            checkbox.focus()
            await pilot.pause()
            assert app.screen.focused is checkbox
            checkbox.toggle()
            await pilot.pause()
            assert checkbox.value is True
            assert app.screen.focused is app.screen.query_one("#ask-ai-input", Input), (
                "toggling SVG mode should hand focus back to the input"
            )

    asyncio.run(driver())


def _claude_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, stdout: str) -> None:
    """Put a fake `claude` that replies with `stdout` on PATH."""
    import os
    import shutil

    from tests.test_ai import _fake_claude

    claude = _fake_claude(tmp_path, stdout=stdout)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(claude, bindir / "claude")
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")


def test_ask_ai_renders_svg_answer_as_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An SVG in the answer is written to a temp file and rendered as an inline Image."""
    import asyncio

    from textual_image.widget import Image

    from mdview.ask_ai import AskAiScreen

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">'
        '<rect width="100" height="40" fill="#4ebf71"/></svg>'
    )
    _claude_on_path(tmp_path, monkeypatch, stdout=f"これは図解です。\n\n{svg}\n\n以上。")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        from textual.widgets import Checkbox

        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.screen.text_select_all()
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen)

            # Opt into SVG diagramming before asking.
            app.screen.query_one("#ask-ai-svg-toggle", Checkbox).value = True
            await pilot.pause()
            await pilot.press("enter")
            images: list[Image] = []
            for _ in range(40):
                await pilot.pause()
                images = list(app.screen.query(Image))
                if images:
                    break
            assert images, "SVG answer should render as an inline Image"
            # The image must live inside the dialog's answer area, i.e. in the popup.
            answer_area = app.screen.query_one("#ask-ai-answer")
            assert list(answer_area.query(Image)), "the diagram should render inside the popup"
            svg_files = list(Path(app._tempdir.name).glob("ask-ai-*.svg"))
            assert svg_files, "the generated SVG should be saved as a temp file"

    asyncio.run(driver())


def test_ask_ai_plain_answer_renders_no_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plain-text answer (no SVG) mounts no Image widget."""
    import asyncio

    from textual_image.widget import Image

    from mdview.ask_ai import AskAiScreen

    _claude_on_path(tmp_path, monkeypatch, stdout="ただのテキスト回答。図はありません。")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.screen.text_select_all()
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen)

            await pilot.press("enter")
            # cwd.log is written by the fake claude when actually invoked, so its
            # presence proves the query ran (not merely that nothing happened).
            cwd_log = tmp_path / "cwd.log"
            for _ in range(40):
                await pilot.pause()
                if cwd_log.exists():
                    break
            assert cwd_log.exists(), "claude should have been invoked"
            for _ in range(5):
                await pilot.pause()
            assert not list(app.screen.query(Image)), "plain text answer needs no Image"

    asyncio.run(driver())


def test_ask_ai_svg_toggle_off_does_not_render_svg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the SVG toggle off (the default), an SVG in the answer is left as
    plain text — no image is rendered."""
    import asyncio

    from textual_image.widget import Image

    from mdview.ask_ai import AskAiScreen

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">'
        '<rect width="100" height="40" fill="#4ebf71"/></svg>'
    )
    _claude_on_path(tmp_path, monkeypatch, stdout=f"説明です。\n\n{svg}\n\n以上。")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.screen.text_select_all()
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen)

            # Leave the toggle off (default) and submit.
            await pilot.press("enter")
            cwd_log = tmp_path / "cwd.log"
            for _ in range(40):
                await pilot.pause()
                if cwd_log.exists():
                    break
            assert cwd_log.exists(), "claude should have been invoked"
            for _ in range(5):
                await pilot.pause()
            assert not list(app.screen.query(Image)), "SVG must not render while the toggle is off"

    asyncio.run(driver())


def test_ask_ai_renders_svg_saved_to_temp_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Claude saves the diagram as a *file* in the temp dir (instead of
    inlining it in stdout), the popup reads that file and renders it inline.

    This is the real-world path: `claude -p` writes the SVG to disk and prints
    only prose, so the popup must scan the dir it told Claude to save into.
    """
    import asyncio
    import os
    import shutil
    import textwrap

    from textual_image.widget import Image

    from mdview.ask_ai import AskAiScreen

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">'
        '<rect width="100" height="40" fill="#d97757"/></svg>'
    )
    # The fake CLI writes the SVG into the dir named by MDVIEW_TEST_SVG_DIR (set
    # by the test to the popup's own output dir) and prints only prose.
    script = tmp_path / "claude"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            pwd > "{tmp_path / 'cwd.log'}"
            mkdir -p "$MDVIEW_TEST_SVG_DIR"
            printf '%s' {svg!r} > "$MDVIEW_TEST_SVG_DIR/diagram.svg"
            printf '%s' '図解を一時フォルダに保存しました。'
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(script, bindir / "claude")
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.screen.text_select_all()
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen)
            # Point the fake CLI at the exact dir the popup will scan.
            monkeypatch.setenv("MDVIEW_TEST_SVG_DIR", str(app.screen._svg_out_dir))

            from textual.widgets import Checkbox

            app.screen.query_one("#ask-ai-svg-toggle", Checkbox).value = True
            await pilot.pause()
            await pilot.press("enter")
            images: list[Image] = []
            for _ in range(40):
                await pilot.pause()
                images = list(app.screen.query(Image))
                if images:
                    break
            assert images, "an SVG saved to the temp dir should render as an Image"
            answer_area = app.screen.query_one("#ask-ai-answer")
            assert list(answer_area.query(Image)), "the diagram should render inside the popup"

    asyncio.run(driver())


def test_clicking_popup_svg_opens_zoom_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rendered SVG in the popup is clickable; a click opens a full-screen zoom."""
    import asyncio

    from mdview.ask_ai import AskAiScreen
    from mdview.image_zoom import ImageZoomScreen, ZoomableImage

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40">'
        '<rect width="100" height="40" fill="#4ebf71"/></svg>'
    )
    _claude_on_path(tmp_path, monkeypatch, stdout=f"図解です。\n\n{svg}\n\n以上。")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.screen.text_select_all()
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen)

            from textual.widgets import Checkbox

            app.screen.query_one("#ask-ai-svg-toggle", Checkbox).value = True
            await pilot.pause()
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause()
                if app.screen.query(ZoomableImage):
                    break
            assert app.screen.query(ZoomableImage), "popup SVG should render as a ZoomableImage"

            await pilot.click(ZoomableImage)
            await pilot.pause()
            assert isinstance(app.screen, ImageZoomScreen), "clicking the SVG should open the zoom screen"

    asyncio.run(driver())


def test_document_svg_renders_as_zoomable_image() -> None:
    """An SVG referenced in the document renders as a clickable ZoomableImage."""
    import asyncio

    from mdview.image_zoom import ZoomableImage

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app.query(ZoomableImage), "sample.svg should render as a ZoomableImage"

    asyncio.run(driver())


def _diff_app(raw: str) -> MdViewerApp:
    """Build a TUI app from a raw unified diff (parse once, pass the model)."""
    from mdview.diff import diff_to_markdown, parse_diff

    files = parse_diff(raw)
    return MdViewerApp(content=diff_to_markdown(files), diff_files=files)


def test_diff_fences_become_delta_hunk_widgets() -> None:
    """A piped diff renders as delta-styled DiffHunk widgets, not raw fences."""
    import asyncio

    from textual.widgets._markdown import MarkdownFence

    from mdview.diff_widget import DiffHunk

    raw = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n-old\n+new\n"

    async def driver() -> None:
        app = _diff_app(raw)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            hunks = list(app.query(DiffHunk))
            assert hunks, "expected a DiffHunk widget"
            # the placeholder ```diff fence has been swapped out
            assert not [
                f for f in app.query(MarkdownFence) if (f.lexer or "").lower() == "diff"
            ]
            shown = str(hunks[0].render())
            assert "old" in shown and "new" in shown

    asyncio.run(driver())


def test_diff_hunk_selection_yields_clean_unified_diff() -> None:
    """Clicking a hunk selects it; the selected text is a valid diff (no gutter)."""
    import asyncio

    from mdview.diff_widget import DiffHunk

    raw = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n-old\n+new\n"

    async def driver() -> None:
        app = _diff_app(raw)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            hunk = app.query(DiffHunk).first()
            await pilot.click(hunk)
            await pilot.pause()
            selected = app.screen.get_selected_text() or ""
            assert selected == "@@ -1,2 +1,2 @@\n-old\n+new", selected

    asyncio.run(driver())


def test_n_navigates_between_file_headings() -> None:
    """With @@ no longer a heading, `n` jumps between the `##` file headings."""
    import asyncio

    from textual.widgets import MarkdownViewer

    raw = "".join(
        f"diff --git a/file{f}.txt b/file{f}.txt\n"
        f"--- a/file{f}.txt\n+++ b/file{f}.txt\n"
        "@@ -1,20 +1,20 @@\n"
        + "".join(f" ctx {f}-{k}\n" for k in range(20))
        + f"-old{f}\n+new{f}\n"
        for f in range(3)
    )

    async def driver() -> None:
        app = _diff_app(raw)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            start = viewer.scroll_y
            await pilot.press("n")
            await pilot.pause()
            assert viewer.scroll_y > start, "`n` should jump to the next file heading"

    asyncio.run(driver())


def test_s_navigates_between_hunks() -> None:
    """`s` jumps to the next hunk within the diff (hunks are no longer headings)."""
    import asyncio

    from textual.widgets import MarkdownViewer

    raw = (
        "diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n"
        "@@ -1,20 +1,20 @@\n"
        + "".join(f" ctx a{k}\n" for k in range(20))
        + "-old1\n+new1\n"
        "@@ -60,20 +60,20 @@\n"
        + "".join(f" ctx b{k}\n" for k in range(20))
        + "-old2\n+new2\n"
    )

    async def driver() -> None:
        app = _diff_app(raw)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            start = viewer.scroll_y
            await pilot.press("s")
            await pilot.pause()
            assert viewer.scroll_y > start, "`s` should jump to the next hunk"

    asyncio.run(driver())


def test_diff_file_heading_hugs_its_first_hunk() -> None:
    """No blank row between a `## file` heading and its first `@@` hunk."""
    import asyncio

    from textual.widgets._markdown import MarkdownHeader

    from mdview.diff_widget import DiffHunk

    raw = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n-a\n+A\n"

    async def driver() -> None:
        app = _diff_app(raw)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            heading = app.query(MarkdownHeader).first()
            hunk = app.query(DiffHunk).first()
            assert hunk.region.y == heading.region.bottom, "the @@ hunk should hug the heading"

    asyncio.run(driver())


def test_embedded_diff_fence_in_markdown_becomes_hunk_widget() -> None:
    """A ```diff fence inside ordinary Markdown is upgraded to a DiffHunk too."""
    import asyncio

    from mdview.diff_widget import DiffHunk

    # Not a whole diff (so diff_files is None) — the embedded-fence branch runs.
    md = "# Doc\n\nExample:\n\n```diff\n-old\n+new\n```\n\nEnd.\n"

    async def driver() -> None:
        app = MdViewerApp(content=md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            hunks = list(app.query(DiffHunk))
            assert len(hunks) == 1
            await pilot.click(hunks[0])
            await pilot.pause()
            assert (app.screen.get_selected_text() or "") == "-old\n+new"

    asyncio.run(driver())


def test_diff_hunk_selection_expands_to_its_file_section() -> None:
    """Clicking a hunk again expands to its `## file` section, not the next file."""
    import asyncio

    from mdview.diff_widget import DiffHunk

    raw = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+A\n"
        "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-b\n+B\n"
    )

    async def driver() -> None:
        app = _diff_app(raw)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            hunk = app.query(DiffHunk).first()  # a.py's hunk
            await pilot.click(hunk)
            await pilot.pause()
            first = app.screen.get_selected_text() or ""
            assert first == "@@ -1 +1 @@\n-a\n+A", first

            await pilot.click(hunk)  # expand one rung → the a.py file section
            await pilot.pause()
            second = app.screen.get_selected_text() or ""
            assert "a.py" in second and "+A" in second, second
            assert "b.py" not in second and "+B" not in second, second
            assert len(second) > len(first)

    asyncio.run(driver())


def test_ask_ai_on_diff_hunk_sends_clean_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selecting a hunk and pressing `h` feeds Ask AI a valid unified diff."""
    import asyncio
    import os
    import shutil

    from tests.test_ai import _fake_claude
    from mdview.ask_ai import AskAiScreen
    from mdview.diff_widget import DiffHunk

    claude = _fake_claude(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(claude, bindir / "claude")
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    raw = "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n-old\n+new\n"

    async def driver() -> None:
        app = _diff_app(raw)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.click(app.query(DiffHunk).first())
            await pilot.pause()
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen)
            assert app.screen._selection == "@@ -1,2 +1,2 @@\n-old\n+new"

    asyncio.run(driver())


def test_mermaid_fence_replaced_when_mmdc_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a fake mmdc on PATH, mermaid fences become Image widgets."""
    import asyncio
    import shutil
    import textwrap

    from tests.test_mermaid import _fake_mmdc  # reuse the bash stub

    mmdc = _fake_mmdc(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(mmdc, bindir / "mmdc")
    (bindir / "mmdc").chmod(0o755)
    import os

    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            from textual.widgets._markdown import MarkdownFence
            from textual_image.widget import Image

            mermaid_fences = [
                f for f in app.query(MarkdownFence) if f.lexer == "mermaid"
            ]
            assert not mermaid_fences, "mermaid fence should be replaced"
            assert list(app.query(Image)), "an Image widget should exist"

    _ = textwrap  # silence unused import; kept for clarity
    asyncio.run(driver())


def test_expand_and_shrink_selection_with_keyboard() -> None:
    """`v` grows the selection along the structure; `V` shrinks it back to nothing."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()

            # Grow: repeated `v` expands monotonically up to the whole document.
            texts: list[str] = []
            for _ in range(5):
                await pilot.press("v")
                await pilot.pause()
                texts.append(app.screen.get_selected_text() or "")

            assert texts[0], "first `v` should select a block"
            assert all(len(b) >= len(a) for a, b in zip(texts, texts[1:])), texts
            assert len(texts[-1]) > len(texts[0]), "selection should grow"
            assert texts[0].strip() in texts[-1], "smaller selection nested in larger"
            assert "mdview サンプル" in texts[-1] and "これでサンプルは終わり" in texts[-1], (
                "largest selection should be the whole document"
            )

            # Shrink: `V` walks back down and eventually clears the selection.
            await pilot.press("V")
            await pilot.pause()
            assert len(app.screen.get_selected_text() or "") < len(texts[-1])

            for _ in range(5):
                await pilot.press("V")
                await pilot.pause()
            assert not (app.screen.get_selected_text() or ""), "shrinking past the block clears"

    asyncio.run(driver())


def test_expand_selection_then_ask_ai_uses_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A keyboard-expanded selection feeds Ask AI just like a mouse selection."""
    import asyncio
    import os
    import shutil

    from tests.test_ai import _fake_claude
    from mdview.ask_ai import AskAiScreen

    claude = _fake_claude(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(claude, bindir / "claude")
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            assert app.screen.get_selected_text(), "`v` should select a block"
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen), "selection should open Ask AI"

    asyncio.run(driver())


def test_mouse_clicks_expand_then_reset_on_new_block() -> None:
    """Clicking a block selects it; clicking it again expands; a new block resets."""
    import asyncio

    from textual.widgets import MarkdownViewer
    from textual.widgets._markdown import MarkdownHeader, MarkdownParagraph

    md = FIXTURES / "sample.md"

    def para(doc, text):
        return next(p for p in doc.query(MarkdownParagraph) if text in str(p._render()))

    def heading(doc, text):
        return next(h for h in doc.query(MarkdownHeader) if text in str(h._render()))

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            doc = app.query_one(MarkdownViewer).document

            target = para(doc, "これは普通の段落")
            target.scroll_visible(animate=False)
            await pilot.pause()

            await pilot.click(target)
            await pilot.pause()
            first = app.screen.get_selected_text() or ""
            assert "太字" in first and "段落と強調" not in first, first

            await pilot.click(target)
            await pilot.pause()
            second = app.screen.get_selected_text() or ""
            assert "段落と強調" in second and len(second) > len(first), second

            # Clicking a different block restarts the ladder at that block.
            other = heading(doc, "mdview サンプル")
            other.scroll_visible(animate=False)
            await pilot.pause()
            await pilot.click(other)
            await pilot.pause()
            third = app.screen.get_selected_text() or ""
            assert third.strip() == "mdview サンプル", third

    asyncio.run(driver())


def test_t_opens_toc_popup_modal() -> None:
    """Pressing `t` opens the TOC as a centered modal screen (not a sidebar)."""
    import asyncio

    from mdview.toc import TocScreen

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("t")
            await pilot.pause()
            assert isinstance(app.screen, TocScreen), "t should push the TOC modal"

    asyncio.run(driver())


def test_toc_popup_lists_document_headings() -> None:
    """The TOC modal's tree is populated with the open document's headings."""
    import asyncio

    from textual.widgets import Tree

    md = FIXTURES / "sample.md"

    def walk(node):
        for child in node.children:
            yield child
            yield from walk(child)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("t")
            await pilot.pause()
            await pilot.pause()
            tree = app.screen.query_one(Tree)
            labels = " ".join(str(node.label) for node in walk(tree.root))
            assert "見出しの階層" in labels, labels
            assert "コードブロック" in labels, labels

    asyncio.run(driver())


def test_toc_popup_jump_scrolls_and_closes() -> None:
    """Selecting a TOC node scrolls the document to it and closes the modal."""
    import asyncio

    from textual.widgets import MarkdownViewer, Tree

    from mdview.toc import TocScreen

    md = FIXTURES / "sample.md"

    def walk(node):
        for child in node.children:
            yield child
            yield from walk(child)

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            assert viewer.scroll_y == 0
            await pilot.press("t")
            await pilot.pause()
            await pilot.pause()
            tree = app.screen.query_one(Tree)
            # "Mermaid" is the last heading, so jumping to it must scroll down.
            target = next(n for n in walk(tree.root) if n.data and "Mermaid" in str(n.label))
            tree.select_node(target)
            await pilot.pause()
            await pilot.pause()
            assert not isinstance(app.screen, TocScreen), "selecting a node should close the modal"
            assert viewer.scroll_y > 0, "selecting a node should scroll the document to it"

    asyncio.run(driver())


def test_toc_popup_escape_closes_without_quitting() -> None:
    """Esc dismisses the TOC modal and returns to the document (does not quit)."""
    import asyncio

    from mdview.toc import TocScreen

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            for close_key in ("escape", "q", "t"):
                await pilot.press("t")
                await pilot.pause()
                assert isinstance(app.screen, TocScreen), f"t should open the modal ({close_key})"
                await pilot.press(close_key)
                await pilot.pause()
                assert not isinstance(app.screen, TocScreen), f"{close_key} should close the modal"
                assert len(app.screen_stack) == 1, f"{close_key} should pop only the modal, not quit"

    asyncio.run(driver())


def test_toc_popup_jk_navigate_tree() -> None:
    """The tree is focused on open and j/k move its cursor."""
    import asyncio

    from textual.widgets import Tree

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("t")
            await pilot.pause()
            await pilot.pause()
            tree = app.screen.query_one(Tree)
            assert tree.has_focus, "tree should be focused so arrows/j/k work immediately"
            # cursor_line is clamped to [0, last]; from the initial -1, j lands on
            # 0 then 1, and k steps back to 0.
            await pilot.press("j")
            await pilot.press("j")
            await pilot.pause()
            two_down = tree.cursor_line
            assert two_down >= 1, two_down
            await pilot.press("k")
            await pilot.pause()
            assert tree.cursor_line == two_down - 1, (two_down, tree.cursor_line)

    asyncio.run(driver())


# --- `/` keyword search ------------------------------------------------------

_MULTI_FILE_DIFF = "".join(
    f"diff --git a/file{f}.txt b/file{f}.txt\n"
    f"--- a/file{f}.txt\n+++ b/file{f}.txt\n"
    "@@ -1,20 +1,20 @@\n"
    + "".join(f" ctx {f}-{k}\n" for k in range(20))
    + f"-old{f}\n+new{f}\n"
    for f in range(3)
)


async def _submit_search(pilot, query: str) -> None:
    """Open the `/` bar, type *query*, and submit it."""
    from textual.widgets import Input

    await pilot.press("slash")
    await pilot.pause()
    pilot.app.query_one("#search-input", Input).value = query
    await pilot.press("enter")
    await pilot.pause()


def test_search_double_at_matches_only_hunks() -> None:
    """`/@@` filters to the diff's hunks (file headings have a single `@`)."""
    import asyncio

    from textual.widgets import MarkdownViewer

    from mdview.diff_widget import DiffHunk

    async def driver() -> None:
        app = _diff_app(_MULTI_FILE_DIFF)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            start = viewer.scroll_y
            await _submit_search(pilot, "@@")
            assert app._search_matches, "expected matches for @@"
            assert all(isinstance(w, DiffHunk) for w in app._search_matches)
            assert len(app._search_matches) == 3
            assert viewer.scroll_y > start, "should jump to the first hunk match"
            # the bar stays visible as a status line while a search is active
            assert app.query_one("#search-bar").display is True
            # exactly one block is marked the "current" one
            current = list(viewer.document.query(".search-current"))
            assert len(current) == 1
            assert current[0] is app._search_hits[app._search_index][0]

    asyncio.run(driver())


def test_search_current_marker_moves_with_n() -> None:
    """The distinct `.search-current` highlight follows `n`/`p`."""
    import asyncio

    from textual.widgets import MarkdownViewer

    async def driver() -> None:
        app = _diff_app(_MULTI_FILE_DIFF)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            await _submit_search(pilot, "old")  # one hit per hunk → distinct blocks
            first = app._search_index
            assert len(list(viewer.document.query(".search-current"))) == 1
            await pilot.press("n")
            await pilot.pause()
            assert app._search_index != first
            current = list(viewer.document.query(".search-current"))
            assert len(current) == 1, "still exactly one current block"
            assert current[0] is app._search_hits[app._search_index][0]

    asyncio.run(driver())


def test_search_steps_through_each_occurrence_in_one_block() -> None:
    """`n` advances one hit at a time, even for two matches in the same block."""
    import asyncio

    md = "# Doc\n\nfoo and foo again\n"

    async def driver() -> None:
        app = MdViewerApp(content=md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _submit_search(pilot, "foo")
            assert len(app._search_hits) == 2, "two occurrences in one paragraph"
            assert app._search_hits[0][0] is app._search_hits[1][0], "same block"
            assert app._search_hits[0][1:] != app._search_hits[1][1:], "different spans"
            first = app._search_index
            await pilot.press("n")
            await pilot.pause()
            assert app._search_index != first, "`n` steps to the 2nd occurrence"

    asyncio.run(driver())


def test_search_anchored_at_matches_only_file_headings() -> None:
    """`/^@ ` filters to the `@ `-prefixed file headings, not the `@@` hunks."""
    import asyncio

    from textual.widgets._markdown import MarkdownHeader

    async def driver() -> None:
        app = _diff_app(_MULTI_FILE_DIFF)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _submit_search(pilot, "^@ ")
            assert len(app._search_matches) == 3
            assert all(isinstance(w, MarkdownHeader) for w in app._search_matches)

    asyncio.run(driver())


def test_search_then_n_p_walk_matches() -> None:
    """While a search is active, `n`/`p` step through the matches."""
    import asyncio

    from textual.widgets import MarkdownViewer

    async def driver() -> None:
        app = _diff_app(_MULTI_FILE_DIFF)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            await _submit_search(pilot, "old")  # one hit per hunk, in separate files
            after_search = viewer.scroll_y
            await pilot.press("n")
            await pilot.pause()
            assert viewer.scroll_y > after_search, "`n` should advance to the next match"
            forward = viewer.scroll_y
            await pilot.press("p")
            await pilot.pause()
            assert viewer.scroll_y < forward, "`p` should step back to the previous match"

    asyncio.run(driver())


def test_empty_search_clears_matches() -> None:
    """Submitting an empty query clears the filter; `n`/`p` revert to headings."""
    import asyncio

    async def driver() -> None:
        app = _diff_app(_MULTI_FILE_DIFF)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _submit_search(pilot, "old")
            assert app._search_hits
            await _submit_search(pilot, "")
            assert app._search_hits == []
            assert app._search_matches == []
            # clearing the search hides the status bar again
            assert app.query_one("#search-bar").display is False

    asyncio.run(driver())


def test_search_no_match_keeps_empty_matches() -> None:
    """A query with no hits leaves nothing to navigate (no stale matches)."""
    import asyncio

    async def driver() -> None:
        app = _diff_app(_MULTI_FILE_DIFF)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _submit_search(pilot, "zzz-no-such-text")
            assert app._search_hits == []
            assert app._search_matches == []

    asyncio.run(driver())


def test_search_colours_only_the_matched_substring() -> None:
    """Highlighting is per-word: only the matched span is washed, not the block."""
    import asyncio

    from textual.widgets._markdown import MarkdownParagraph

    md = "# Doc\n\nalpha import beta gamma\n"

    async def driver() -> None:
        app = MdViewerApp(content=md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _submit_search(pilot, "import")
            para = next(
                w for w in app._search_matches if isinstance(w, MarkdownParagraph)
            )
            text = para._content.plain
            start = text.index("import")
            end = start + len("import")
            spans = para._content._spans
            # a highlight span covers exactly "import" — not the whole paragraph
            assert any(s.start == start and s.end == end for s in spans), spans
            assert not any(s.start == 0 and s.end == len(text) for s in spans), spans

    asyncio.run(driver())
