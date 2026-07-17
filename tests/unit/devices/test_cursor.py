from bittty import Board
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT


def test_set_cursor():
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
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
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.set_position(10, 5)
    terminal.board.cursor.carriage_return()
    assert terminal.board.cursor.x == 0
    assert terminal.board.cursor.y == 5


def test_line_feed():
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
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
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
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
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.x = 10
    terminal.board.cursor.y = 5
    terminal.board.cursor.save()

    terminal.board.cursor.x = 20
    terminal.board.cursor.y = 15

    terminal.board.cursor.restore()
    assert terminal.board.cursor.x == 10
    assert terminal.board.cursor.y == 5


def test_backspace_wrap():
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.x = 0
    terminal.board.cursor.y = 5
    terminal.board.cursor.backspace()
    assert terminal.board.cursor.x == 79
    assert terminal.board.cursor.y == 4


def test_cursor_device_owns_position_and_save_restore():
    terminal = Board(width=10, height=5)
    cursor = terminal.board.cursor

    cursor.set_position(4, 2)
    terminal.board.style.current_ansi_code = "\x1b[31m"
    cursor.save()

    cursor.set_position(9, 4)
    terminal.board.style.current_ansi_code = "\x1b[32m"
    cursor.restore()

    assert (cursor.x, cursor.y) == (4, 2)
    assert terminal.board.style.current_ansi_code == "\x1b[31m"


def test_cursor_device_tabs_and_basic_movement():
    terminal = Board(width=12, height=5)
    cursor = terminal.board.cursor

    cursor.set_position(3, 2)
    cursor.set_tab_stop()
    cursor.set_position(0, 2)
    cursor.horizontal_tab()
    assert cursor.x == 3

    cursor.move_forward(20)
    assert cursor.x == 11
    cursor.move_back(20)
    assert cursor.x == 0
    cursor.move_up(20)
    assert cursor.y == 0
    cursor.move_down(20)
    assert cursor.y == 4


def test_cursor_device_line_feed_scrolls_screen_region():
    terminal = Board(width=8, height=3)
    terminal.board.screen.current_buffer.set(0, 0, "top")
    terminal.board.screen.current_buffer.set(0, 1, "mid")
    terminal.board.screen.current_buffer.set(0, 2, "bot")

    terminal.board.cursor.set_position(0, 2)
    terminal.board.cursor.line_feed()

    assert terminal.board.cursor.y == 2
    assert terminal.board.screen.current_buffer.get_line_text(0).startswith("mid")
    assert terminal.board.screen.current_buffer.get_line_text(1).startswith("bot")


def test_cursor_device_text_write_wrap_preparation():
    terminal = Board(width=4, height=3)
    cursor = terminal.board.cursor

    cursor.x = 4
    cursor.y = 0
    cursor.prepare_for_text_write()

    assert (cursor.x, cursor.y) == (0, 1)


def test_origin_mode_column_is_relative_to_left_margin():
    terminal = Board(width=20, height=10)
    terminal.parser.feed("\x1b[?69h")  # DECLRMM
    terminal.parser.feed("\x1b[5;15s")  # DECSLRM: margins at columns 5-15
    terminal.parser.feed("\x1b[?6h")  # DECOM

    terminal.parser.feed("\x1b[1;1H")  # home is the margin corner under origin mode
    assert terminal.board.cursor.x == 4

    terminal.parser.feed("\x1b[1;99H")  # clamped inside the right margin
    assert terminal.board.cursor.x == 14
