from bittty.parser import Parser
from bittty.constants import BS, HT


def test_backspace(board):
    """Test that backspace moves the cursor back."""
    parser = Parser(board)

    # Write some text first
    parser.feed("Hello")
    assert board.cursor.x == 5

    # Send backspace
    parser.feed(BS)

    # Cursor should move back
    assert board.cursor.x == 4


def test_horizontal_tab(board):
    """Test that a horizontal tab moves the cursor to the next tab stop."""
    parser = Parser(board)

    # Move cursor to position 2
    parser.feed("ab")
    assert board.cursor.x == 2

    # Send horizontal tab
    parser.feed(HT)

    # Should move to next tab stop (8)
    assert board.cursor.x == 8


def test_horizontal_tab_uses_set_tab_stop(board):
    """ESC H should set a tab stop used by subsequent horizontal tabs."""
    parser = Parser(board)

    board.cursor.set_position(3, 0)
    parser.feed("\x1bH")
    board.cursor.set_position(0, 0)
    parser.feed(HT)

    assert board.cursor.x == 3


def test_line_feed(board):
    """Test that a line feed moves the cursor down."""
    parser = Parser(board)
    initial_y = board.cursor.y

    parser.feed("\x0a")  # Line feed

    # Cursor should move down one line
    assert board.cursor.y == initial_y + 1


def test_carriage_return(board):
    """Test that a carriage return moves the cursor to the beginning of the line."""
    parser = Parser(board)

    # Move cursor to the right
    parser.feed("Hello World")
    assert board.cursor.x > 0

    # Send carriage return
    parser.feed("\x0d")

    # Cursor should be at beginning of line
    assert board.cursor.x == 0
