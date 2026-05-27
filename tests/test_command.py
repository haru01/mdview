from mdview.command import parse_command


def test_quit_spellings() -> None:
    assert parse_command("q") == "quit"
    assert parse_command("quit") == "quit"


def test_help_spellings() -> None:
    assert parse_command("h") == "help"
    assert parse_command("help") == "help"


def test_whitespace_and_case_are_ignored() -> None:
    assert parse_command("  Q  ") == "quit"
    assert parse_command("Help") == "help"


def test_empty_is_none() -> None:
    assert parse_command("") is None
    assert parse_command("   ") is None


def test_unknown_is_none() -> None:
    assert parse_command("xyz") is None
    assert parse_command("quitnow") is None
