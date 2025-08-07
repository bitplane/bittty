from bittty.parser import Parser
from bittty.constants import BS, HT


def test_backspace(terminal):
    """Test that backspace moves the cursor back."""
    parser = Parser(terminal)

    # Write some text first
    parser.feed("Hello")
    assert terminal.cursor_x == 5

    # Send backspace
    parser.feed(BS)

    # Cursor should move back
    assert terminal.cursor_x == 4


def test_horizontal_tab(terminal):
    """Test that a horizontal tab moves the cursor to the next tab stop."""
    parser = Parser(terminal)

    # Move cursor to position 2
    parser.feed("ab")
    assert terminal.cursor_x == 2

    # Send horizontal tab
    parser.feed(HT)

    # Should move to next tab stop (8)
    assert terminal.cursor_x == 8


def test_line_feed(terminal):
    """Test that a line feed moves the cursor down."""
    parser = Parser(terminal)
    initial_y = terminal.cursor_y

    parser.feed("\x0a")  # Line feed

    # Cursor should move down one line
    assert terminal.cursor_y == initial_y + 1


def test_carriage_return(terminal):
    """Test that a carriage return moves the cursor to the beginning of the line."""
    parser = Parser(terminal)

    # Move cursor to the right
    parser.feed("Hello World")
    assert terminal.cursor_x > 0

    # Send carriage return
    parser.feed("\x0d")

    # Cursor should be at beginning of line
    assert terminal.cursor_x == 0
