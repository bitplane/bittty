"""Tests for OSC (Operating System Command) sequences."""

from bittty import Board, MemoryConnection
from bittty.constants import (
    DEFAULT_TERMINAL_HEIGHT,
    DEFAULT_TERMINAL_WIDTH,
)
from bittty.parser import Parser


def render_terminal_to_string(board: Board) -> str:
    """Render the terminal content to a plain string for testing."""
    return "\n".join(render_lines_to_string(board.get_content()))


def render_lines_to_string(lines: list[list[tuple[str, str]]]) -> list[str]:
    """Render a list of lines to a list of strings for testing."""
    output = []
    for line in lines:
        output.append("".join(char for _, char in line))
    return output


def test_osc_set_both_window_and_icon_title():
    """Test OSC 0 for setting both window and icon title."""
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(board)

    # OSC 0 sets both window and icon title
    # Format: ESC ] 0 ; <title> BEL
    title_sequence = "\x1b]0;My Board Window\x07"
    parser.feed(title_sequence)

    # Check that both titles are set
    assert board.title.title == "My Board Window"
    assert board.title.icon_title == "My Board Window"

    # Window title should not appear in screen content
    output = render_terminal_to_string(board)
    assert "My Board Window" not in output
    assert output.strip() == ""  # Screen should be empty


def test_osc_window_title_with_text():
    """Test OSC sequence followed by regular text."""
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(board)

    # OSC sequence followed by text
    data = "\x1b]0;Board Title\x07Hello World"
    parser.feed(data)

    # Only "Hello World" should be visible
    output = render_terminal_to_string(board)
    assert "Board Title" not in output
    assert "Hello World" in output


def test_ps1_osc_title_sequence():
    """Test PS1 prompt with OSC (Operating System Command) sequences."""
    # Your PS1: \[\e]0;\u@\h: \w\a\]${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$
    # Let's break it down:
    # \[\e]0;...\a\] - OSC sequence to set terminal title
    # \[\033[01;32m\] - Green bold
    # \[\033[00m\] - Reset
    # \[\033[01;34m\] - Blue bold

    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(board)

    # Simulate a typical PS1 prompt output
    # The \e]0;user@host: /path\a part is an OSC sequence that sets the window title
    ps1_text = "\x1b]0;user@host: /home/user\x07user@host:/home/user$ "

    parser.feed(ps1_text)

    # The OSC sequence should not appear in the visible output
    output = render_terminal_to_string(board)
    assert "user@host: /home/user" not in output  # This is the window title, shouldn't be visible
    assert "user@host:/home/user$ " in output  # This is the actual prompt

    # Check cursor position is after the prompt
    assert board.cursor.x == len("user@host:/home/user$ ")


def test_ps1_with_colors():
    """Test PS1 with color escape sequences."""
    board = Board(width=80, height=24)
    parser = Parser(board)

    # Simplified PS1 with colors: green username, blue path
    # \033[01;32m = bold green
    # \033[01;34m = bold blue
    # \033[00m = reset
    ps1_text = "\x1b[01;32muser@host\x1b[00m:\x1b[01;34m~/projects\x1b[00m$ "

    parser.feed(ps1_text)

    # Check the text content
    output = render_terminal_to_string(board)
    assert "user@host:~/projects$ " in output

    # Check that styles were applied correctly
    # We expect specific ANSI sequences to be present on the page
    # This is a simplified check, as full ANSI parsing is complex
    line_cells = board.blitter.current_page.get_content()[0]

    # Check for bold green for "user@host" - now using Style objects
    from bittty.style import Color, Style

    bold_green_style = Style(fg=Color("indexed", 2), bold=True)
    assert (bold_green_style, "u") in line_cells

    # Check for bold blue for "~/projects"
    bold_blue_style = Style(fg=Color("indexed", 4), bold=True)
    assert (bold_blue_style, "~") in line_cells

    # Check for default style (after reset)
    default_style = Style()
    assert (default_style, ":") in line_cells or (default_style, "$") in line_cells


def test_osc_string_terminator():
    """Test OSC with ST (String Terminator) instead of BEL."""
    board = Board(width=80, height=24)
    parser = Parser(board)

    # OSC can be terminated with ST (ESC \) instead of BEL
    # Format: ESC ] 0 ; <title> ESC \\
    title_sequence = "\x1b]0;My Title\x1b\\"
    parser.feed(title_sequence)

    # Title should not appear in screen content
    output = render_terminal_to_string(board)
    assert "My Title" not in output


def test_osc_set_icon_title():
    """Test OSC 1 for setting icon title only."""
    board = Board(width=80, height=24)
    parser = Parser(board)

    # OSC 1 sets icon title
    parser.feed("\x1b]1;Icon Title\x07")

    # Should set icon title attribute
    assert board.title.icon_title == "Icon Title"


def test_osc_set_window_title_only():
    """Test OSC 2 for setting window title only."""
    board = Board(width=80, height=24)
    parser = Parser(board)

    # OSC 2 sets window title only
    parser.feed("\x1b]2;Window Title\x07")

    # Should set window title attribute
    assert board.title.title == "Window Title"


def test_osc_unknown_command():
    """Test OSC with unknown command number."""
    board = Board(width=80, height=24)
    parser = Parser(board)

    # OSC with unknown command - should be consumed without error
    parser.feed("\x1b]999;unknown data\x07")
    parser.feed("Hello")

    # Should still work normally after unknown OSC
    output = render_terminal_to_string(board)
    assert "Hello" in output


def test_osc_malformed_command():
    """Test OSC with malformed command."""
    board = Board(width=80, height=24)
    parser = Parser(board)

    # OSC with non-numeric command
    parser.feed("\x1b]abc;data\x07")
    parser.feed("Test")

    # Should still work normally after malformed OSC
    output = render_terminal_to_string(board)
    assert "Test" in output


def test_osc_empty_command():
    """Test OSC with empty string."""
    board = Board(width=80, height=24)
    parser = Parser(board)

    # Empty OSC
    parser.feed("\x1b]\x07")
    parser.feed("Normal text")

    # Should work normally
    output = render_terminal_to_string(board)
    assert "Normal text" in output


def test_osc_set_empty_title_and_icon():
    """Test OSC 0 with an empty title string."""
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(board)

    # Set initial titles
    board.title.set_title("Initial Title")
    board.title.set_icon_title("Initial Icon")

    # OSC 0 with empty title should clear both
    parser.feed("\x1b]0;\x07")

    assert board.title.title == ""
    assert board.title.icon_title == ""


def test_osc_set_title_and_icon_no_semicolon():
    """Test OSC 0 without a semicolon separator."""
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(board)

    # Set initial titles
    board.title.set_title("Initial Title")
    board.title.set_icon_title("Initial Icon")

    # OSC 0 without a semicolon should be ignored
    parser.feed("\x1b]0My Title\x07")

    assert board.title.title == "Initial Title"
    assert board.title.icon_title == "Initial Icon"


def test_osc_repeated_query_runs_each_time():
    """Repeated OSC queries must not be skipped by function-level caching."""
    board = Board(width=80, height=24)
    parser = Parser(board)
    transport = MemoryConnection()
    board.host.attach(transport)

    parser.feed("\x1b]10;?\x07")
    parser.feed("\x1b]10;?\x07")

    assert transport.data == [
        "\033]10;rgb:ffff/ffff/ffff\007",
        "\033]10;rgb:ffff/ffff/ffff\007",
    ]


def test_osc_same_sequence_applies_to_different_boards():
    """OSC dispatch mutates the target terminal and must not cache by sequence only."""
    first = Board(width=80, height=24)
    second = Board(width=80, height=24)

    Parser(first).feed("\x1b]2;Shared Title\x07")
    Parser(second).feed("\x1b]2;Shared Title\x07")

    assert first.title.title == "Shared Title"
    assert second.title.title == "Shared Title"
