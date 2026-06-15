from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import DirectoryTree, MarkdownViewer

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


def test_event_flow_fences_are_replaced_with_widgets() -> None:
    """An ```event-flow-svg fence is swapped for an EventFlow widget; no such fence remains."""
    import asyncio

    md = FIXTURES / "eventflow.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            from textual.widgets._markdown import MarkdownFence

            from mdview.eventflow_widget import EventFlow

            flows = list(app.query(EventFlow))
            assert len(flows) == 2, "expected one EventFlow per event-flow-svg fence"

            remaining = [
                f
                for f in app.query(MarkdownFence)
                if (f.lexer or "").lower() == "event-flow-svg"
            ]
            assert not remaining, "event-flow-svg fences must be removed after injection"

    asyncio.run(driver())


def test_shift_right_scrolls_a_wide_flow() -> None:
    """shift+right scrolls the visible event flow horizontally."""
    import asyncio

    md = FIXTURES / "eventflow.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(40, 24)) as pilot:  # narrow: flow overflows
            await pilot.pause()
            await pilot.pause()
            from mdview.eventflow_widget import EventFlow

            flow = next(iter(app.query(EventFlow)))
            before = flow.scroll_offset.x
            await pilot.press("shift+right")
            await pilot.pause()
            assert flow.scroll_offset.x > before

    asyncio.run(driver())


def test_event_flow_selection_yields_dsl() -> None:
    """Selecting a whole flow (the ladder's top rung) yields its DSL, not box-art."""
    import asyncio

    md = FIXTURES / "eventflow.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            from textual.selection import SELECT_ALL

            from mdview.eventflow_widget import EventFlow

            flow = next(iter(app.query(EventFlow)))
            text, _ = flow.get_selection(SELECT_ALL)
            assert "|community|" in text
            assert "┌" not in text  # box-art excluded

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


def test_brackets_navigate_between_headings() -> None:
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

            await pilot.press("right_square_bracket")
            await pilot.pause()
            after_first = viewer.scroll_y
            assert after_first > start, "`]` should move scroll down to next heading"

            await pilot.press("right_square_bracket")
            await pilot.pause()
            after_second = viewer.scroll_y
            assert after_second > after_first, "`]` should advance further"

            await pilot.press("left_square_bracket")
            await pilot.pause()
            after_prev = viewer.scroll_y
            assert after_prev < after_second, "`[` should move back to previous heading"

    asyncio.run(driver())


def test_ctrl_bracket_navigates_only_h2_headings() -> None:
    """Ctrl+]/Ctrl+[ jump between `##` (H2) sections, skipping H1/H3."""
    import asyncio

    from textual.widgets import MarkdownViewer

    md = (
        "# Title\n\nintro\n\n"
        "## Section A\n\n" + "aaa\n\n" * 20
        + "### Sub A1\n\n" + "xxx\n\n" * 20
        + "## Section B\n\n" + "bbb\n\n" * 20
        + "### Sub B1\n\n" + "yyy\n\n" * 20
    )

    async def driver() -> None:
        app = MdViewerApp(content=md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            assert len(app._headings_at_level(2)) == 2, "two ## sections"
            assert len(app._all_headings()) == 5, "H1 + 2×H2 + 2×H3"
            sub_a1_y = app._headings_at_level(3)[0].virtual_region.y
            section_b_y = app._headings_at_level(2)[1].virtual_region.y

            # Plain `]` stops at every heading, so the 2nd press lands on the H3.
            await pilot.press("right_square_bracket")
            await pilot.press("right_square_bracket")
            await pilot.pause()
            assert abs(viewer.scroll_y - sub_a1_y) <= 2, "`]` stops at the H3"

            # Ctrl+] skips the H3: from the top, the 2nd press reaches Section B.
            await pilot.press("g")
            await pilot.pause()
            await pilot.press("ctrl+right_square_bracket")
            await pilot.press("ctrl+right_square_bracket")
            await pilot.pause()
            assert abs(viewer.scroll_y - section_b_y) <= 2, "Ctrl+] skips the H3 to the 2nd H2"

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
    """`Backspace` keybinding pops history and reloads the prior file."""
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

            await pilot.press("backspace")
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
    """`?` opens the help screen; `h` is Ask AI now and must not open help."""
    import asyncio

    from mdview.help import HelpScreen

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen), "`?` should open the help screen"
            await pilot.press("question_mark")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen), "`?` should close the help screen"
            # `h` (no selection) warns for Ask AI rather than opening help.
            await pilot.press("h")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen), "`h` should not open help"

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

            # SVG diagramming is on by default: the toggle starts checked.
            toggle = app.screen.query_one("#ask-ai-svg-toggle", Checkbox)
            assert toggle.value is True, "SVG mode should be on by default"

            # The popup is enlarged for research-style reading.
            dialog = app.screen.query_one("#ask-ai-dialog")
            assert dialog.styles.width.value == 90
            assert dialog.styles.height.value == 90

    asyncio.run(driver())


def test_ask_ai_context_click_opens_full_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clicking the Ask AI context opens a nested modal with the full selection."""
    import asyncio
    import os
    import shutil

    from tests.test_ai import _fake_claude
    from mdview.ask_ai import AskAiScreen, SelectionViewScreen

    claude = _fake_claude(tmp_path)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    shutil.copy(claude, bindir / "claude")
    (bindir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")

    # A long body so the context preview truncates and the popup adds value.
    md = "# Title\n\n" + "word " * 100 + "\n"

    async def driver() -> None:
        app = MdViewerApp(content=md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            app.screen.text_select_all()
            await pilot.pause()
            selection = app.screen.get_selected_text()
            assert selection and len(selection) > 200, "selection should exceed the preview cap"
            await pilot.press("h")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen)

            await pilot.click("#ask-ai-context")
            await pilot.pause()
            assert isinstance(app.screen, SelectionViewScreen), "click opens the full-text modal"
            assert app.screen._text == selection, "modal holds the full (untruncated) selection"
            # Non-diff prose is re-rendered with a Markdown widget (same colours
            # and line spacing as the main view), not a syntax-highlighted Static.
            from textual.widgets import Markdown

            assert app.screen.query("#selection-view-body Markdown"), "renders via Markdown"

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen), "Esc returns to Ask AI (no quit)"

            # `q` also closes the full-text modal.
            await pilot.click("#ask-ai-context")
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            assert isinstance(app.screen, AskAiScreen)

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
            assert checkbox.value is False
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
    """With the SVG toggle off, an SVG in the answer is left as
    plain text — no image is rendered."""
    import asyncio

    from textual.widgets import Checkbox
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

            # Turn the toggle off and submit.
            app.screen.query_one("#ask-ai-svg-toggle", Checkbox).value = False
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


def test_bracket_navigates_between_file_headings() -> None:
    """With @@ no longer a heading, `]` jumps between the `##` file headings."""
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
            await pilot.press("right_square_bracket")
            await pilot.pause()
            assert viewer.scroll_y > start, "`]` should jump to the next file heading"

    asyncio.run(driver())


def test_brace_navigates_between_hunks() -> None:
    """`}` jumps to the next hunk within the diff (hunks are no longer headings)."""
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
            await pilot.press("right_curly_bracket")
            await pilot.pause()
            assert viewer.scroll_y > start, "`}` should jump to the next hunk"

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


def test_escape_clears_selection_and_next_v_starts_small() -> None:
    """Esc drops the current selection and resets the ladder; next `v` is small."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            small = app.screen.get_selected_text() or ""
            assert small, "first `v` selects the smallest block"
            await pilot.press("v")
            await pilot.press("v")
            await pilot.pause()
            grown = app.screen.get_selected_text() or ""
            assert len(grown) > len(small), "selection grew with more `v`"

            await pilot.press("escape")
            await pilot.pause()
            assert not (app.screen.get_selected_text() or ""), "Esc clears the selection"
            assert app._sel_scopes is None
            assert app._sel_index == 0
            assert app._sel_anchor is None

            # The ladder is reset, so `v` restarts at the smallest block.
            await pilot.press("v")
            await pilot.pause()
            restarted = app.screen.get_selected_text() or ""
            assert restarted.strip() == small.strip(), "next `v` starts small again"

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
    """Open the command line in search mode, type the query, and submit it."""
    from textual.widgets import Input

    await pilot.press("slash")
    await pilot.pause()
    pilot.app.query_one("#cmdline", Input).value = query
    await pilot.press("enter")
    await pilot.pause()


def test_search_aborts_on_catastrophic_pattern() -> None:
    """A backtracking-pathological regex aborts within the budget, not hangs."""
    import asyncio
    import time

    md = "# T\n\n" + "a" * 50 + "!\n"  # long run that defeats `(a|a)*$`

    async def driver() -> None:
        app = MdViewerApp(content=md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            started = time.monotonic()
            await _submit_search(pilot, "(a|a)*$")
            assert time.monotonic() - started < 5, "search must not hang"
            assert app._search_hits == [], "pathological search yields no hits"
            assert "複雑" in str(app.query_one("#cmdline-count").render())

    asyncio.run(driver())


def test_navigation_clears_active_search(tmp_path) -> None:
    """Following a link (or Backspace back) drops the previous doc's search state."""
    import asyncio

    a = tmp_path / "a.md"
    a.write_text("# A\n\napple apple here\n\n[to B](b.md)\n", encoding="utf-8")
    b = tmp_path / "b.md"
    b.write_text("# B\n\nbanana content\n", encoding="utf-8")

    async def driver() -> None:
        app = MdViewerApp(a)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _submit_search(pilot, "apple")
            assert app._search_hits, "search should be active on doc A"
            await app._load_file(b)  # simulate navigating to doc B
            await pilot.pause()
            assert app._search_hits == [], "stale hits must be cleared on nav"
            assert app._search_matches == []
            assert app.query_one("#cmdline-bar").display is False, "bar hidden after nav"

    asyncio.run(driver())


def test_search_bar_shows_less_style_slash_prompt() -> None:
    """The bar reads like less: a fixed `/` prompt label, empty editable field."""
    import asyncio

    from textual.widgets import Input, Static

    async def driver() -> None:
        app = MdViewerApp(content="# T\n\nalpha beta\n")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            assert str(app.query_one("#cmdline-prompt", Static).render()) == "/"
            assert app.query_one("#cmdline", Input).value == "", "field holds only the query"

    asyncio.run(driver())


def test_cmdline_prompt_label_reflects_mode() -> None:
    """`/` and `:` set a fixed prompt label; the editable field stays content-only
    (a typed char never overwrites the prompt)."""
    import asyncio

    from textual.widgets import Input, Static

    async def driver() -> None:
        app = MdViewerApp(content="# T\n\nalpha\n")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            prompt = app.query_one("#cmdline-prompt", Static)
            box = app.query_one("#cmdline", Input)
            await pilot.press("colon")
            await pilot.pause()
            assert str(prompt.render()) == ":" and app._cmdline_mode == "command"
            await pilot.press("w")
            await pilot.pause()
            assert box.value == "w", "the typed char does not overwrite the `:` prompt"

    asyncio.run(driver())


def test_search_reopens_prefilled_with_slash_and_last_query() -> None:
    """Re-opening with `/` prefills the field as `/<last query>`."""
    import asyncio

    from textual.widgets import Input

    async def driver() -> None:
        app = MdViewerApp(content="# T\n\nalpha alpha\n")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _submit_search(pilot, "alpha")
            assert app._search_hits, "search is active"
            await pilot.press("slash")
            await pilot.pause()
            assert app.query_one("#cmdline", Input).value == "alpha", "field prefilled"
            from textual.widgets import Static

            assert str(app.query_one("#cmdline-prompt", Static).render()) == "/"

    asyncio.run(driver())


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
            assert app.query_one("#cmdline-bar").display is True
            # exactly one block is marked the "current" one
            current = list(viewer.document.query(".search-current"))
            assert len(current) == 1
            assert current[0] is app._search_hits[app._search_index][0]

    asyncio.run(driver())


def test_search_current_marker_moves_with_n() -> None:
    """The distinct `.search-current` highlight follows `n`/`N`."""
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


def test_search_then_n_N_walk_matches() -> None:
    """While a search is active, `n`/`N` step through the matches."""
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
            await pilot.press("N")
            await pilot.pause()
            assert viewer.scroll_y < forward, "`N` should step back to the previous match"

    asyncio.run(driver())


def test_empty_search_clears_matches() -> None:
    """Submitting an empty query clears the filter; `n`/`N` become no-ops."""
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
            assert app.query_one("#cmdline-bar").display is False

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


# --- `:` command line, help screen, Esc/cancel, paging ----------------------


async def _submit_command(pilot, text: str) -> None:
    """Open the command line in command mode, type `:text`, and submit it."""
    from textual.widgets import Input

    await pilot.press("colon")
    await pilot.pause()
    pilot.app.query_one("#cmdline", Input).value = text
    await pilot.press("enter")
    await pilot.pause()


def test_colon_q_quits() -> None:
    """`:q` exits the app (and so does single `q`)."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            exits: list[bool] = []
            app.exit = lambda *a, **k: exits.append(True)  # type: ignore[method-assign]
            await _submit_command(pilot, "q")
            assert exits == [True], "`:q` should call exit()"
            assert app.query_one("#cmdline-bar").display is False
            await pilot.press("q")
            await pilot.pause()
            assert exits == [True, True], "single `q` should also exit"

    asyncio.run(driver())


def test_typed_colon_q_quits_via_keystrokes() -> None:
    """Regression: opening with `:` then typing `q` runs the *command* (quit), not
    a search for "q". The fixed prompt keeps the field content-only (`q`)."""
    import asyncio

    from textual.widgets import Input

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            exits: list[bool] = []
            app.exit = lambda *a, **k: exits.append(True)  # type: ignore[method-assign]
            await pilot.press("colon")
            await pilot.press("q")
            await pilot.pause()
            assert app.query_one("#cmdline", Input).value == "q", "field is content-only"
            await pilot.press("enter")
            await pilot.pause()
            assert exits == [True], "typed `:q` should quit, not search"

    asyncio.run(driver())


def test_typed_slash_search_via_keystrokes() -> None:
    """Opening with `/` then typing a pattern runs a search."""
    import asyncio

    from textual.widgets import Input

    async def driver() -> None:
        app = MdViewerApp(content="# T\n\nalpha beta alpha\n")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("slash")
            for ch in "alpha":
                await pilot.press(ch)
            await pilot.pause()
            assert app.query_one("#cmdline", Input).value == "alpha"
            await pilot.press("enter")
            await pilot.pause()
            assert app._search_hits, "typed `/alpha` should find matches"

    asyncio.run(driver())


def test_help_screen_scrolls_with_keys_not_the_background() -> None:
    """Movement keys scroll the help modal's body, not the document behind it."""
    import asyncio

    from textual.containers import VerticalScroll
    from textual.widgets import MarkdownViewer

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        # A small screen makes the cheat-sheet overflow so it actually scrolls.
        async with app.run_test(size=(48, 10)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            bg = viewer.scroll_y
            await pilot.press("question_mark")
            await pilot.pause()
            body = app.screen.query_one("#help-body", VerticalScroll)
            assert body.max_scroll_y > 0, "help should overflow at this size"
            await pilot.press("space")
            await pilot.pause()
            assert body.scroll_y > 0, "Space scrolls the help body"
            assert viewer.scroll_y == bg, "the background document must not move"
            await pilot.press("g")
            await pilot.pause()
            assert body.scroll_y == 0, "`g` returns the help body to the top"

    asyncio.run(driver())


def test_toc_movement_keys_do_not_scroll_background() -> None:
    """In the TOC modal, page/top/bottom keys drive the tree, not the document."""
    import asyncio

    from textual.widgets import MarkdownViewer

    from mdview.toc import TocScreen

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(60, 12)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            assert viewer.max_scroll_y > 0, "document must be scrollable to be meaningful"
            await pilot.press("t")
            await pilot.pause()
            assert isinstance(app.screen, TocScreen)
            bg = viewer.scroll_y
            for key in ("d", "G", "f", "pagedown"):
                await pilot.press(key)
                await pilot.pause()
            assert viewer.scroll_y == bg, "TOC movement keys must not scroll the document"

    asyncio.run(driver())


def test_colon_h_opens_help_screen() -> None:
    """`:h` opens the help screen; Esc closes it without quitting."""
    import asyncio

    from mdview.help import HelpScreen

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            await _submit_command(pilot, "h")
            assert isinstance(app.screen, HelpScreen), "`:h` should open help"
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen), "Esc closes the help screen"

    asyncio.run(driver())


def test_unknown_command_notifies_and_does_not_quit() -> None:
    """An unrecognised `:cmd` warns and closes the bar; it must not exit."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            exits: list[bool] = []
            app.exit = lambda *a, **k: exits.append(True)  # type: ignore[method-assign]
            await _submit_command(pilot, "nope")
            assert exits == [], "unknown command must not quit"
            assert app.query_one("#cmdline-bar").display is False

    asyncio.run(driver())


def test_escape_does_not_quit_at_idle() -> None:
    """Esc with nothing active is a no-op — crucially, it must not exit."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            exits: list[bool] = []
            app.exit = lambda *a, **k: exits.append(True)  # type: ignore[method-assign]
            await pilot.press("escape")
            await pilot.pause()
            assert exits == [], "Esc must not quit the app"

    asyncio.run(driver())


def test_escape_clears_active_search_without_quitting() -> None:
    """With a search active, Esc clears it (bar hidden, hits dropped); no quit."""
    import asyncio

    async def driver() -> None:
        app = _diff_app(_MULTI_FILE_DIFF)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            exits: list[bool] = []
            app.exit = lambda *a, **k: exits.append(True)  # type: ignore[method-assign]
            await _submit_search(pilot, "old")
            assert app._search_hits, "search should be active"
            await pilot.press("escape")
            await pilot.pause()
            assert app._search_hits == [], "Esc should clear the search"
            assert app.query_one("#cmdline-bar").display is False
            assert exits == [], "Esc must not quit while clearing a search"

    asyncio.run(driver())


def test_command_line_escape_cancels_without_running() -> None:
    """Esc in the `:` box closes it without dispatching anything or quitting."""
    import asyncio

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            exits: list[bool] = []
            app.exit = lambda *a, **k: exits.append(True)  # type: ignore[method-assign]
            await pilot.press("colon")
            await pilot.pause()
            assert app.query_one("#cmdline-bar").display is True
            await pilot.press("escape")
            await pilot.pause()
            assert app.query_one("#cmdline-bar").display is False
            assert exits == [], "cancelling the command line must not quit"

    asyncio.run(driver())


def test_paging_keys_scroll() -> None:
    """`f`/Space page down, `b`/PageUp page up."""
    import asyncio

    from textual.widgets import MarkdownViewer

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            start = viewer.scroll_y
            await pilot.press("f")
            await pilot.pause()
            down = viewer.scroll_y
            assert down > start, "`f` should page down"
            await pilot.press("b")
            await pilot.pause()
            assert viewer.scroll_y < down, "`b` should page back up"

    asyncio.run(driver())


def test_space_navigates_headings_in_prose() -> None:
    """In a normal doc, Space/Shift+Space step between headings."""
    import asyncio

    from textual.widgets import MarkdownViewer

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            start = viewer.scroll_y
            await pilot.press("space")
            await pilot.pause()
            first = viewer.scroll_y
            assert first > start, "Space should jump to the next heading"
            await pilot.press("space")
            await pilot.pause()
            second = viewer.scroll_y
            assert second > first, "Space should advance further"
            await pilot.press("shift+space")
            await pilot.pause()
            assert viewer.scroll_y < second, "Shift+Space should step back"

    asyncio.run(driver())


def test_space_walks_files_and_hunks_in_diff() -> None:
    """In a diff, Space stops at file headings and `@@` hunks (both)."""
    import asyncio

    from textual.widgets import MarkdownViewer

    async def driver() -> None:
        app = _diff_app(_MULTI_FILE_DIFF)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            # The combined target set is headings + hunks, so Space has more
            # stops than the heading-only `]` walk.
            sections = app._section_targets()
            headings = app._all_headings()
            assert len(sections) > len(headings), "diff sections include hunks too"
            start = viewer.scroll_y
            await pilot.press("space")
            await pilot.pause()
            assert viewer.scroll_y > start, "Space should advance through the diff"

    asyncio.run(driver())


def test_n_is_noop_without_active_search() -> None:
    """`n`/`N` only move with a search active; `]` always walks headings."""
    import asyncio

    from textual.widgets import MarkdownViewer

    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            start = viewer.scroll_y
            await pilot.press("n")
            await pilot.pause()
            assert viewer.scroll_y == start, "`n` should do nothing without a search"
            await pilot.press("right_square_bracket")
            await pilot.pause()
            assert viewer.scroll_y > start, "`]` should still jump to the next heading"

    asyncio.run(driver())


def test_drag_selection_is_not_overwritten_by_click() -> None:
    """ドラッグ(押下位置≠離した位置)の自由選択を on_click が上書きしないこと。"""
    import asyncio

    from textual.events import Click
    from textual.geometry import Offset
    from textual.selection import Selection
    from textual.widgets import MarkdownViewer
    from textual.widgets._markdown import MarkdownParagraph

    async def driver() -> None:
        app = MdViewerApp(content="# Title\n\nHello world paragraph for selection.\n")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            para = next(iter(viewer.document.query(MarkdownParagraph)))

            # 押下位置を実イベントで記録(on_mouse_down が配線されている確認も兼ねる)
            await pilot.mouse_down(para, offset=(0, 0))
            down = app._mouse_down_offset
            assert down is not None, "on_mouse_down should record the press offset"

            # ドラッグが作った細かい選択を模した番兵を置く
            sentinel = {para: Selection(Offset(0, 0), Offset(5, 0))}
            app.screen.selections = sentinel
            app._sel_scopes = None

            # ドラッグ終了時に発火する Click を、押下位置とは別のセルで流す
            click = Click(
                widget=para,
                x=0,
                y=0,
                delta_x=0,
                delta_y=0,
                button=0,
                shift=False,
                meta=False,
                ctrl=False,
                screen_x=down.x + 5,
                screen_y=down.y,
                chain=1,
            )
            app.on_click(click)
            await pilot.pause()

            # 自由選択が残り、セマンティックの梯子は始まっていない
            assert app.screen.selections == sentinel, (
                "a drag's freeform selection must survive the trailing Click"
            )
            assert app._sel_scopes is None, "drag must not start the semantic ladder"

    asyncio.run(driver())


def test_stationary_click_still_selects_block() -> None:
    """ドラッグなしの単発クリックは従来どおりブロック単位のセマンティック選択になること。"""
    import asyncio

    from textual.widgets import MarkdownViewer
    from textual.widgets._markdown import MarkdownParagraph

    async def driver() -> None:
        app = MdViewerApp(content="# Title\n\nHello world paragraph for selection.\n")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            para = next(iter(viewer.document.query(MarkdownParagraph)))

            # pilot.click は MouseDown→MouseUp→Click を同一オフセットで送る = 静止クリック
            await pilot.click(para, offset=(2, 0))
            await pilot.pause()

            assert app._sel_scopes is not None, "a stationary click should start a selection"
            assert app.screen.get_selected_text(), "the clicked block's text should be selected"

    asyncio.run(driver())


# ===== Section insight (`##` heading lightbulb → treasure) =====

_INSIGHT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="30">'
    '<rect width="80" height="30" fill="#4ebf71"/></svg>'
)


def test_section_insight_lightbulb_added_to_each_h2(monkeypatch: pytest.MonkeyPatch) -> None:
    """With `claude` available, every `##` heading gains a trailing 💡, and the
    marker does not leak into the heading's selectable text."""
    import asyncio

    from textual.selection import SELECT_ALL
    from textual.widgets._markdown import MarkdownH2

    monkeypatch.setattr("mdview.app.find_claude", lambda: "claude")
    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            h2s = list(app.query(MarkdownH2))
            assert h2s, "sample should contain H2 headings"
            for h in h2s:
                assert h._content.plain.rstrip().endswith("💡"), h._content.plain
            # The marker is stripped from selected/copied text.
            app.screen.selections = {h2s[0]: SELECT_ALL}
            assert "💡" not in (app.screen.get_selected_text() or "")

    asyncio.run(driver())


def test_section_insight_not_added_without_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    """No `claude` on PATH → the feature degrades to nothing (no marker)."""
    import asyncio

    from textual.widgets._markdown import MarkdownH2

    monkeypatch.setattr("mdview.app.find_claude", lambda: None)
    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            for h in app.query(MarkdownH2):
                assert "💡" not in h._content.plain

    asyncio.run(driver())


def test_section_insight_run_turns_lightbulb_into_treasure_and_opens_modal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clicking the 💡 runs claude on that section, turns it into 📦, and a
    second click opens the explanation modal."""
    import asyncio

    from mdview.section_insight import SectionInsightScreen

    monkeypatch.setattr("mdview.app.find_claude", lambda: "claude")

    async def fake_ask(
        selection, question, document, *, claude, cwd,
        svg_out_dir=None, concise_svg=False, timeout=120.0,
    ):
        assert selection.startswith("## "), "the section's own Markdown is sent"
        assert document, "the whole document is sent as context"
        if svg_out_dir is not None:
            svg_out_dir.mkdir(parents=True, exist_ok=True)
            (svg_out_dir / "diagram.svg").write_text(_INSIGHT_SVG, encoding="utf-8")
        return "このセクションの解説です。"

    monkeypatch.setattr("mdview.app.ask_claude", fake_ask)
    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            hid = next(iter(app._insight_headings))
            heading = app._insight_headings[hid]

            app.action_section_insight(hid)
            for _ in range(60):
                await pilot.pause()
                if app._insight_state[hid].status == "done":
                    break
            assert app._insight_state[hid].status == "done"
            assert heading._content.plain.rstrip().endswith("📦"), heading._content.plain
            assert app._insight_state[hid].prose == "このセクションの解説です。"
            assert app._insight_state[hid].svgs, "the saved SVG should be collected"

            app.action_section_insight(hid)
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, SectionInsightScreen)

    asyncio.run(driver())


def test_section_insight_caps_concurrency_at_three(monkeypatch: pytest.MonkeyPatch) -> None:
    """At most three sections generate at once; a fourth request is refused with
    a notice and starts no worker."""
    import asyncio

    monkeypatch.setattr("mdview.app.find_claude", lambda: "claude")
    release = asyncio.Event()

    async def blocking_ask(
        selection, question, document, *, claude, cwd,
        svg_out_dir=None, concise_svg=False, timeout=120.0,
    ):
        await release.wait()
        return "done"

    monkeypatch.setattr("mdview.app.ask_claude", blocking_ask)
    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            hids = list(app._insight_headings)[:4]
            assert len(hids) == 4, "sample needs at least four H2 sections"

            notes: list[tuple] = []
            app.notify = lambda *a, **k: notes.append((a, k))  # type: ignore[method-assign]

            for hid in hids[:3]:
                app.action_section_insight(hid)
            assert app._insight_running == 3

            app.action_section_insight(hids[3])
            assert app._insight_running == 3, "the 4th request must not start a worker"
            assert app._insight_state[hids[3]].status == "idle"
            assert any("最大3件" in str(a[0]) for a, _ in notes if a), notes

            release.set()
            for _ in range(80):
                await pilot.pause()
                if app._insight_running == 0:
                    break
            assert app._insight_running == 0

    asyncio.run(driver())


def test_section_insight_uses_extended_timeout_and_concise_svg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Section insight runs with a longer timeout and asks for a simple diagram
    (the Ask AI defaults of 120s / full-detail SVG stay untouched)."""
    import asyncio

    captured: dict = {}

    async def fake_ask(
        selection, question, document, *, claude, cwd,
        svg_out_dir=None, concise_svg=False, timeout=120.0,
    ):
        captured["timeout"] = timeout
        captured["concise_svg"] = concise_svg
        return "ok"

    monkeypatch.setattr("mdview.app.find_claude", lambda: "claude")
    monkeypatch.setattr("mdview.app.ask_claude", fake_ask)
    md = FIXTURES / "sample.md"

    async def driver() -> None:
        app = MdViewerApp(md)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            hid = next(iter(app._insight_headings))
            app.action_section_insight(hid)
            for _ in range(60):
                await pilot.pause()
                if app._insight_state[hid].status == "done":
                    break
            assert captured["timeout"] == 240.0
            assert captured["concise_svg"] is True

    asyncio.run(driver())


_DIFF_TWO_FILES = (
    "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
    "@@ -1,2 +1,2 @@\n-old_x\n+new_x\n"
    "diff --git a/y.py b/y.py\n--- a/y.py\n+++ b/y.py\n"
    "@@ -1,2 +1,2 @@\n-old_y\n+new_y\n"
)


def test_diff_file_headings_gain_insight_lightbulb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opening a diff gives each `## @ file` heading a clickable 💡, just like a
    prose section heading (the feature is no longer skipped for diffs)."""
    import asyncio

    from textual.widgets._markdown import MarkdownH2

    monkeypatch.setattr("mdview.app.find_claude", lambda: "claude")

    async def driver() -> None:
        app = _diff_app(_DIFF_TWO_FILES)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            assert app._diff_files is not None
            assert len(app._insight_headings) == 2, "one marker per diffed file"
            for h in app.query(MarkdownH2):
                assert h._content.plain.rstrip().endswith("💡"), h._content.plain

    asyncio.run(driver())


def test_diff_insight_uses_diff_question(monkeypatch: pytest.MonkeyPatch) -> None:
    """For a diff, the insight prompt is `_DIFF_INSIGHT_QUESTION` (about the
    change), not the prose `_INSIGHT_QUESTION`; the file's diff is the selection."""
    import asyncio

    from mdview.app import _DIFF_INSIGHT_QUESTION

    captured: dict = {}

    async def fake_ask(
        selection, question, document, *, claude, cwd,
        svg_out_dir=None, concise_svg=False, timeout=120.0,
    ):
        captured["question"] = question
        captured["selection"] = selection
        return "この差分の解説です。"

    monkeypatch.setattr("mdview.app.find_claude", lambda: "claude")
    monkeypatch.setattr("mdview.app.ask_claude", fake_ask)

    async def driver() -> None:
        app = _diff_app(_DIFF_TWO_FILES)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            hid = next(iter(app._insight_headings))
            app.action_section_insight(hid)
            for _ in range(60):
                await pilot.pause()
                if app._insight_state[hid].status == "done":
                    break
            assert captured["question"] == _DIFF_INSIGHT_QUESTION
            assert "@ x.py" in captured["selection"], captured["selection"]
            assert "```diff" in captured["selection"]

    asyncio.run(driver())


def test_diff_insight_run_opens_modal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clicking a diff file's 💡 runs claude, turns it into 📦, and a second click
    opens the same explanation modal used for prose sections."""
    import asyncio

    from mdview.section_insight import SectionInsightScreen

    monkeypatch.setattr("mdview.app.find_claude", lambda: "claude")

    async def fake_ask(
        selection, question, document, *, claude, cwd,
        svg_out_dir=None, concise_svg=False, timeout=120.0,
    ):
        if svg_out_dir is not None:
            svg_out_dir.mkdir(parents=True, exist_ok=True)
            (svg_out_dir / "diagram.svg").write_text(_INSIGHT_SVG, encoding="utf-8")
        return "この差分の解説です。"

    monkeypatch.setattr("mdview.app.ask_claude", fake_ask)

    async def driver() -> None:
        app = _diff_app(_DIFF_TWO_FILES)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            hid = next(iter(app._insight_headings))
            heading = app._insight_headings[hid]
            app.action_section_insight(hid)
            for _ in range(60):
                await pilot.pause()
                if app._insight_state[hid].status == "done":
                    break
            assert app._insight_state[hid].status == "done"
            assert heading._content.plain.rstrip().endswith("📦"), heading._content.plain
            assert app._insight_state[hid].svgs, "the saved SVG should be collected"

            app.action_section_insight(hid)
            await pilot.pause()
            await pilot.pause()
            assert isinstance(app.screen, SectionInsightScreen)

    asyncio.run(driver())


def test_external_change_reloads_in_place() -> None:
    """An external write is picked up by `_reload_from_disk`, updating the buffer
    and the disk baseline while preserving scroll position."""
    import asyncio

    async def driver(tmp: Path) -> None:
        target = tmp / "doc.md"
        target.write_text("# 元の見出し\n\n本文\n", encoding="utf-8")
        app = MdViewerApp(target)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            assert "元の見出し" in viewer.document.source

            target.write_text("# 新しい見出し\n\n書き換え後\n", encoding="utf-8")
            await app._reload_from_disk()
            await pilot.pause()

            assert "新しい見出し" in viewer.document.source
            assert app._disk_baseline == "# 新しい見出し\n\n書き換え後\n"
            assert not app._is_dirty()

    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as d:
        asyncio.run(driver(Path(d)))


def test_external_change_preserves_scroll() -> None:
    """A reload keeps the reader's scroll position (via _rerender_preserving_scroll)."""
    import asyncio

    long_doc = "# 見出し\n\n" + "\n\n".join(f"段落 {i}" for i in range(200)) + "\n"

    async def driver(tmp: Path) -> None:
        target = tmp / "long.md"
        target.write_text(long_doc, encoding="utf-8")
        app = MdViewerApp(target)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            viewer.scroll_to(y=40, animate=False)
            await pilot.pause()
            before = viewer.scroll_y
            assert before > 0

            target.write_text(long_doc + "\n追記\n", encoding="utf-8")
            await app._reload_from_disk()
            await pilot.pause()

            assert abs(viewer.scroll_y - before) <= 2

    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as d:
        asyncio.run(driver(Path(d)))


def test_reload_discards_unsaved_edits() -> None:
    """When dirty, an external change still reloads and drops the undo stack."""
    import asyncio

    async def driver(tmp: Path) -> None:
        target = tmp / "doc.md"
        target.write_text("# 元\n\n本文\n", encoding="utf-8")
        app = MdViewerApp(target)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            # Simulate an in-memory AI edit: buffer diverges from disk baseline.
            app._undo_stack.append(viewer.document.source)
            await viewer.document.update("# 元\n\n編集後の本文\n")
            assert app._is_dirty()

            target.write_text("# 外部更新\n\n別の本文\n", encoding="utf-8")
            await app._reload_from_disk()
            await pilot.pause()

            assert "外部更新" in viewer.document.source
            assert app._undo_stack == []
            assert not app._is_dirty()

    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as d:
        asyncio.run(driver(Path(d)))


def test_reload_noop_when_content_identical() -> None:
    """A reload whose disk content equals the buffer only resyncs the baseline."""
    import asyncio

    async def driver(tmp: Path) -> None:
        target = tmp / "doc.md"
        text = "# 見出し\n\n本文\n"
        target.write_text(text, encoding="utf-8")
        app = MdViewerApp(target)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.pause()
            viewer = app.query_one(MarkdownViewer)
            doc_obj = viewer.document
            app._disk_baseline = "stale"  # prove the guard resyncs it
            await app._reload_from_disk()
            await pilot.pause()
            # Same document instance (no re-render) and baseline resynced.
            assert app.query_one(MarkdownViewer).document is doc_obj
            assert app._disk_baseline == text

    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as d:
        asyncio.run(driver(Path(d)))


def test_watcher_started_for_file_not_for_stdin() -> None:
    """A file-backed document starts a watch worker; a stdin document does not."""
    import asyncio

    async def driver(tmp: Path) -> None:
        target = tmp / "doc.md"
        target.write_text("# 見出し\n", encoding="utf-8")
        file_app = MdViewerApp(target)
        async with file_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert file_app._watch_task is not None

        stdin_app = MdViewerApp(content="# 見出し\n")
        async with stdin_app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert stdin_app._watch_task is None

    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as d:
        asyncio.run(driver(Path(d)))


def test_y_copies_selection_to_clipboard() -> None:
    """`y` copies the current selection to the clipboard via OSC52."""
    import asyncio

    md = FIXTURES / "simple.md"

    async def scenario() -> None:
        app = MdViewerApp(md)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("v")
            await pilot.pause()
            assert app.screen.get_selected_text(), "`v` should select a block"
            await pilot.press("y")
            await pilot.pause()
            assert app.clipboard
            assert app.clipboard.strip() != ""

    asyncio.run(scenario())


def test_y_without_selection_notifies_and_keeps_clipboard_empty() -> None:
    """`y` with no selection notifies and leaves the clipboard empty."""
    import asyncio

    md = FIXTURES / "simple.md"

    async def scenario() -> None:
        app = MdViewerApp(md)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
            assert app.clipboard == ""

    asyncio.run(scenario())


def test_load_file_renders_diff_as_hunks() -> None:
    """Loading a .diff via _load_file renders delta-style hunks, not a code block."""
    import asyncio

    from mdview.diff_widget import DiffHunk

    async def scenario() -> None:
        app = MdViewerApp(FIXTURES / "simple.md")
        async with app.run_test() as pilot:
            await app._load_file(FIXTURES / "sample.diff")
            await pilot.pause()
            assert app.query(DiffHunk)
            assert app._diff_files is not None

    asyncio.run(scenario())


def test_external_change_to_diff_file_keeps_delta_rendering(tmp_path) -> None:
    """An external edit to a loaded diff file stays delta-rendered, not raw."""
    import asyncio

    from mdview.diff_widget import DiffHunk

    async def scenario() -> None:
        diff_a = (
            "--- a/foo.py\n+++ b/foo.py\n@@ -1,2 +1,2 @@\n"
            "-old line\n+new line\n unchanged\n"
        )
        diff_b = (
            "--- a/foo.py\n+++ b/foo.py\n@@ -1,2 +1,2 @@\n"
            "-old line\n+changed again\n unchanged\n"
        )
        diff_path = tmp_path / "x.diff"
        diff_path.write_text(diff_a)
        app = MdViewerApp(diff_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query(DiffHunk)  # delta-rendered on initial load
            assert app._diff_files is not None
            diff_path.write_text(diff_b)  # external edit
            await app._reload_from_disk()
            await pilot.pause()
            assert app.query(DiffHunk)  # STILL delta, not raw markdown
            assert app._diff_files is not None

    asyncio.run(scenario())


def test_e_toggles_sidebar_visibility():
    import asyncio

    async def scenario():
        app = MdViewerApp(FIXTURES / "simple.md")
        async with app.run_test() as pilot:
            # Single-file launch: the sidebar is not mounted until first opened
            # (a DirectoryTree's resident loader worker would otherwise hang
            # App.workers.wait_for_complete()).
            assert not app.query("#sidebar")
            await pilot.press("e")
            await pilot.pause()
            sidebar = app.query_one("#sidebar", DirectoryTree)
            assert sidebar.display
            assert app.focused is sidebar
            await pilot.press("e")
            await pilot.pause()
            assert not sidebar.display

    asyncio.run(scenario())


def test_selecting_tree_file_switches_viewer():
    import asyncio

    async def scenario():
        app = MdViewerApp(FIXTURES / "simple.md", root_dir=FIXTURES)
        async with app.run_test() as pilot:
            await pilot.pause()
            sidebar = app.query_one("#sidebar", DirectoryTree)
            target = (FIXTURES / "sample.diff").resolve()
            app.on_directory_tree_file_selected(
                DirectoryTree.FileSelected(sidebar.root, target)
            )
            for _ in range(20):
                await pilot.pause()
                if app._md_path == target:
                    break
            assert app._md_path == target

    asyncio.run(scenario())


def test_directory_launch_shows_sidebar_and_opens_readme(tmp_path):
    import asyncio
    from mdview.filetree import initial_file

    async def scenario():
        (tmp_path / "README.md").write_text("# Readme\n\nbody\n")
        (tmp_path / "other.md").write_text("# Other\n")
        first = initial_file(tmp_path)
        app = MdViewerApp(first, root_dir=tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            sidebar = app.query_one("#sidebar", DirectoryTree)
            assert sidebar.display
            assert app._md_path == (tmp_path / "README.md").resolve()

    asyncio.run(scenario())


def test_empty_directory_launch_shows_placeholder(tmp_path):
    import asyncio
    from mdview.filetree import initial_file

    async def scenario():
        (tmp_path / "notes.txt").write_text("not markdown")
        first = initial_file(tmp_path)  # None — no viewable file
        app = MdViewerApp(first, root_dir=tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._md_path is None
            assert app.query_one("#sidebar", DirectoryTree).display

    asyncio.run(scenario())


def test_write_with_no_file_open_is_safe(tmp_path):
    import asyncio
    from mdview.filetree import initial_file

    async def scenario():
        (tmp_path / "notes.txt").write_text("x")  # no viewable file
        app = MdViewerApp(initial_file(tmp_path), root_dir=tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._md_path is None
            ok = app._write_file()
            await pilot.pause()
            assert ok is False  # refused, no crash

    asyncio.run(scenario())


def test_back_after_opening_from_empty_dir_is_safe(tmp_path):
    import asyncio
    from mdview.filetree import initial_file

    async def scenario():
        (tmp_path / "notes.txt").write_text("x")
        app = MdViewerApp(initial_file(tmp_path), root_dir=tmp_path)  # _md_path None
        doc = tmp_path / "doc.md"
        doc.write_text("# Doc\n\nbody\n")
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._md_path is None
            sidebar = app.query_one("#sidebar", DirectoryTree)
            app.on_directory_tree_file_selected(
                DirectoryTree.FileSelected(sidebar.root, doc.resolve())
            )
            for _ in range(20):
                await pilot.pause()
                if app._md_path == doc.resolve():
                    break
            assert app._md_path == doc.resolve()
            assert app._history == []  # no (None, ...) entry recorded
            app.action_go_back()  # must not crash
            await pilot.pause()
            await pilot.pause()

    asyncio.run(scenario())
