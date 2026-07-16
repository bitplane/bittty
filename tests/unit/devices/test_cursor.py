from bittty.terminal import Terminal
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT


def test_set_cursor():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.set_position(10, 5)
    assert terminal.board.cursor.x == 10
    assert terminal.board.cursor.y == 5

    # Test out of bounds clamping
    terminal.board.cursor.set_position(100, 30)
    assert terminal.board.cursor.x == 79  # width - 1
    assert terminal.board.cursor.y == 23  # height - 1

    terminal.board.cursor.set_position(-5, -5)
    assert terminal.board.cursor.x == 0
    assert terminal.board.cursor.y == 0


def test_carriage_return():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.set_position(10, 5)
    terminal.board.cursor.carriage_return()
    assert terminal.board.cursor.x == 0
    assert terminal.board.cursor.y == 5


def test_line_feed():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.set_position(10, 5)
    terminal.board.cursor.line_feed()
    assert terminal.board.cursor.x == 10
    assert terminal.board.cursor.y == 6

    # Test line feed at bottom of terminal (should scroll)
    terminal.board.cursor.set_position(0, terminal.height - 1)
    terminal.board.cursor.line_feed()
    assert terminal.board.cursor.y == terminal.height - 1  # Cursor stays at bottom
    # (Scrolling content is tested in test_scroll.py)


def test_backspace():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.set_position(10, 5)
    terminal.board.cursor.backspace()
    assert terminal.board.cursor.x == 9
    assert terminal.board.cursor.y == 5

    # Test backspace at beginning of line (should wrap)
    terminal.board.cursor.set_position(0, 5)
    terminal.board.cursor.backspace()
    assert terminal.board.cursor.x == 79
    assert terminal.board.cursor.y == 4

    # Test backspace at 0,0 (should stay at 0,0)
    terminal.board.cursor.set_position(0, 0)
    terminal.board.cursor.backspace()
    assert terminal.board.cursor.x == 0
    assert terminal.board.cursor.y == 0


def test_save_restore_cursor():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.x = 10
    terminal.board.cursor.y = 5
    terminal.board.cursor.save()

    terminal.board.cursor.x = 20
    terminal.board.cursor.y = 15

    terminal.board.cursor.restore()
    assert terminal.board.cursor.x == 10
    assert terminal.board.cursor.y == 5


def test_backspace_wrap():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.x = 0
    terminal.board.cursor.y = 5
    terminal.board.cursor.backspace()
    assert terminal.board.cursor.x == 79
    assert terminal.board.cursor.y == 4
