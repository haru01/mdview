from mdview.command import parse_command


def test_quit_spellings() -> None:
    assert parse_command("q") == "quit"
    assert parse_command("quit") == "quit"


def test_help_spellings() -> None:
    assert parse_command("h") == "help"
    assert parse_command("help") == "help"


def test_edit_loop_commands() -> None:
    assert parse_command("w") == "write"
    assert parse_command("write") == "write"
    assert parse_command("q!") == "force_quit"
    assert parse_command("wq") == "write_quit"
    assert parse_command("x") == "write_quit"
    assert parse_command("undo") == "undo"
    assert parse_command("u") == "undo"


def test_quick_open_commands() -> None:
    assert parse_command("e") == "open"
    assert parse_command("edit") == "open"
    assert parse_command("open") == "open"
    assert parse_command("o") == "open"


def test_whitespace_and_case_are_ignored() -> None:
    assert parse_command("  Q  ") == "quit"
    assert parse_command("Help") == "help"
    assert parse_command(" W ") == "write"
    assert parse_command("Q!") == "force_quit"


def test_empty_is_none() -> None:
    assert parse_command("") is None
    assert parse_command("   ") is None


def test_unknown_is_none() -> None:
    assert parse_command("xyz") is None
    assert parse_command("quitnow") is None
