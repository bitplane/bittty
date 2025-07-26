from bittty.terminal import Terminal
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT


def test_set_cursor():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.set_cursor(10, 5)
    assert terminal.cursor_x == 10
    assert terminal.cursor_y == 5

    # Test out of bounds clamping
    terminal.set_cursor(100, 30)
    assert terminal.cursor_x == 79  # width - 1
    assert terminal.cursor_y == 23  # height - 1

    terminal.set_cursor(-5, -5)
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 0


def test_carriage_return():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.set_cursor(10, 5)
    terminal.carriage_return()
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 5


def test_line_feed():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.set_cursor(10, 5)
    terminal.line_feed()
    assert terminal.cursor_x == 10
    assert terminal.cursor_y == 6

    # Test line feed at bottom of terminal (should scroll)
    terminal.set_cursor(0, terminal.height - 1)
    terminal.line_feed()
    assert terminal.cursor_y == terminal.height - 1  # Cursor stays at bottom
    # (Scrolling content is tested in test_scroll.py)


def test_backspace():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.set_cursor(10, 5)
    terminal.backspace()
    assert terminal.cursor_x == 9
    assert terminal.cursor_y == 5

    # Test backspace at beginning of line (should wrap)
    terminal.set_cursor(0, 5)
    terminal.backspace()
    assert terminal.cursor_x == 79
    assert terminal.cursor_y == 4

    # Test backspace at 0,0 (should stay at 0,0)
    terminal.set_cursor(0, 0)
    terminal.backspace()
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 0


def test_save_restore_cursor():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.cursor_x = 10
    terminal.cursor_y = 5
    terminal.save_cursor()

    terminal.cursor_x = 20
    terminal.cursor_y = 15

    terminal.restore_cursor()
    assert terminal.cursor_x == 10
    assert terminal.cursor_y == 5


def test_backspace_wrap():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.cursor_x = 0
    terminal.cursor_y = 5
    terminal.backspace()
    assert terminal.cursor_x == 79
    assert terminal.cursor_y == 4
