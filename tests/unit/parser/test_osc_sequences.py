"""Tests for OSC (Operating System Command) sequences."""

from bittty.parser import Parser
from bittty.terminal import Terminal
from bittty.constants import (
    DEFAULT_TERMINAL_WIDTH,
    DEFAULT_TERMINAL_HEIGHT,
)


def render_terminal_to_string(terminal: Terminal) -> str:
    """Render the terminal content to a plain string for testing."""
    return "\n".join(render_lines_to_string(terminal.get_content()))


def render_lines_to_string(lines: list[list[tuple[str, str]]]) -> list[str]:
    """Render a list of lines to a list of strings for testing."""
    output = []
    for line in lines:
        output.append("".join(char for _, char in line))
    return output


def test_osc_set_both_window_and_icon_title():
    """Test OSC 0 for setting both window and icon title."""
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal)

    # OSC 0 sets both window and icon title
    # Format: ESC ] 0 ; <title> BEL
    title_sequence = "\x1b]0;My Terminal Window\x07"
    parser.feed(title_sequence)

    # Check that both titles are set
    assert terminal.title == "My Terminal Window"
    assert terminal.icon_title == "My Terminal Window"

    # Window title should not appear in screen content
    output = render_terminal_to_string(terminal)
    assert "My Terminal Window" not in output
    assert output.strip() == ""  # Screen should be empty


def test_osc_window_title_with_text():
    """Test OSC sequence followed by regular text."""
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal)

    # OSC sequence followed by text
    data = "\x1b]0;Terminal Title\x07Hello World"
    parser.feed(data)

    # Only "Hello World" should be visible
    output = render_terminal_to_string(terminal)
    assert "Terminal Title" not in output
    assert "Hello World" in output


def test_ps1_osc_title_sequence():
    """Test PS1 prompt with OSC (Operating System Command) sequences."""
    # Your PS1: \[\e]0;\u@\h: \w\a\]${debian_chroot:+($debian_chroot)}\[\033[01;32m\]\u@\h\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$
    # Let's break it down:
    # \[\e]0;...\a\] - OSC sequence to set terminal title
    # \[\033[01;32m\] - Green bold
    # \[\033[00m\] - Reset
    # \[\033[01;34m\] - Blue bold

    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal)

    # Simulate a typical PS1 prompt output
    # The \e]0;user@host: /path\a part is an OSC sequence that sets the window title
    ps1_text = "\x1b]0;user@host: /home/user\x07user@host:/home/user$ "

    parser.feed(ps1_text)

    # The OSC sequence should not appear in the visible output
    output = render_terminal_to_string(terminal)
    assert "user@host: /home/user" not in output  # This is the window title, shouldn't be visible
    assert "user@host:/home/user$ " in output  # This is the actual prompt

    # Check cursor position is after the prompt
    assert terminal.cursor_x == len("user@host:/home/user$ ")


def test_ps1_with_colors():
    """Test PS1 with color escape sequences."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Simplified PS1 with colors: green username, blue path
    # \033[01;32m = bold green
    # \033[01;34m = bold blue
    # \033[00m = reset
    ps1_text = "\x1b[01;32muser@host\x1b[00m:\x1b[01;34m~/projects\x1b[00m$ "

    parser.feed(ps1_text)

    # Check the text content
    output = render_terminal_to_string(terminal)
    assert "user@host:~/projects$ " in output

    # Check that styles were applied correctly
    # We expect specific ANSI sequences to be present in the buffer
    # This is a simplified check, as full ANSI parsing is complex
    line_cells = terminal.current_buffer.get_content()[0]

    # Check for bold green for "user@host" - now using Style objects
    from bittty.style import Style, Color

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
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # OSC can be terminated with ST (ESC \) instead of BEL
    # Format: ESC ] 0 ; <title> ESC \\
    title_sequence = "\x1b]0;My Title\x1b\\"
    parser.feed(title_sequence)

    # Title should not appear in screen content
    output = render_terminal_to_string(terminal)
    assert "My Title" not in output


def test_osc_set_icon_title():
    """Test OSC 1 for setting icon title only."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # OSC 1 sets icon title
    parser.feed("\x1b]1;Icon Title\x07")

    # Should set icon title attribute
    assert terminal.icon_title == "Icon Title"


def test_osc_set_window_title_only():
    """Test OSC 2 for setting window title only."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # OSC 2 sets window title only
    parser.feed("\x1b]2;Window Title\x07")

    # Should set window title attribute
    assert terminal.title == "Window Title"


def test_osc_unknown_command():
    """Test OSC with unknown command number."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # OSC with unknown command - should be consumed without error
    parser.feed("\x1b]999;unknown data\x07")
    parser.feed("Hello")

    # Should still work normally after unknown OSC
    output = render_terminal_to_string(terminal)
    assert "Hello" in output


def test_osc_malformed_command():
    """Test OSC with malformed command."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # OSC with non-numeric command
    parser.feed("\x1b]abc;data\x07")
    parser.feed("Test")

    # Should still work normally after malformed OSC
    output = render_terminal_to_string(terminal)
    assert "Test" in output


def test_osc_empty_command():
    """Test OSC with empty string."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Empty OSC
    parser.feed("\x1b]\x07")
    parser.feed("Normal text")

    # Should work normally
    output = render_terminal_to_string(terminal)
    assert "Normal text" in output


def test_osc_set_empty_title_and_icon():
    """Test OSC 0 with an empty title string."""
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal)

    # Set initial titles
    terminal.set_title("Initial Title")
    terminal.set_icon_title("Initial Icon")

    # OSC 0 with empty title should clear both
    parser.feed("\x1b]0;\x07")

    assert terminal.title == ""
    assert terminal.icon_title == ""


def test_osc_set_title_and_icon_no_semicolon():
    """Test OSC 0 without a semicolon separator."""
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal)

    # Set initial titles
    terminal.set_title("Initial Title")
    terminal.set_icon_title("Initial Icon")

    # OSC 0 without a semicolon should be ignored
    parser.feed("\x1b]0My Title\x07")

    assert terminal.title == "Initial Title"
    assert terminal.icon_title == "Initial Icon"
