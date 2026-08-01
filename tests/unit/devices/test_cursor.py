from bittty import Board
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT


def test_set_cursor():
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    board.cursor.set_position(10, 5)
    assert board.cursor.x == 10
    assert board.cursor.y == 5

    # Test out of bounds clamping
    board.cursor.set_position(100, 30)
    assert board.cursor.x == 79  # width - 1
    assert board.cursor.y == 23  # height - 1

    board.cursor.set_position(-5, -5)
    assert board.cursor.x == 0
    assert board.cursor.y == 0


def test_carriage_return():
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    board.cursor.set_position(10, 5)
    board.cursor.carriage_return()
    assert board.cursor.x == 0
    assert board.cursor.y == 5


def test_line_feed():
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    board.cursor.set_position(10, 5)
    board.cursor.line_feed()
    assert board.cursor.x == 10
    assert board.cursor.y == 6

    # Test line feed at bottom of terminal (should scroll)
    board.cursor.set_position(0, board.height - 1)
    board.cursor.line_feed()
    assert board.cursor.y == board.height - 1  # Cursor stays at bottom
    # (Scrolling content is tested in test_scroll.py)


def test_backspace():
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    board.cursor.set_position(10, 5)
    board.cursor.backspace()
    assert board.cursor.x == 9
    assert board.cursor.y == 5

    # Backspace stops at the left margin.
    board.cursor.set_position(0, 5)
    board.cursor.backspace()
    assert board.cursor.x == 0
    assert board.cursor.y == 5

    # Test backspace at 0,0 (should stay at 0,0)
    board.cursor.set_position(0, 0)
    board.cursor.backspace()
    assert board.cursor.x == 0
    assert board.cursor.y == 0


def test_save_restore_cursor():
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    board.cursor.x = 10
    board.cursor.y = 5
    board.cursor.save()

    board.cursor.x = 20
    board.cursor.y = 15

    board.cursor.restore()
    assert board.cursor.x == 10
    assert board.cursor.y == 5


def test_backspace_stops_at_left_margin():
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    board.cursor.x = 0
    board.cursor.y = 5
    board.cursor.backspace()
    assert board.cursor.x == 0
    assert board.cursor.y == 5


def test_cursor_device_owns_position_and_save_restore():
    board = Board(width=10, height=5)
    cursor = board.cursor

    cursor.set_position(4, 2)
    board.style.current_ansi_code = "\x1b[31m"
    cursor.save()

    cursor.set_position(9, 4)
    board.style.current_ansi_code = "\x1b[32m"
    cursor.restore()

    assert (cursor.x, cursor.y) == (4, 2)
    assert board.style.current_ansi_code == "\x1b[31m"


def test_cursor_device_tabs_and_basic_movement():
    board = Board(width=12, height=5)
    cursor = board.cursor

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
    board = Board(width=8, height=3)
    board.blitter.current_page.set(0, 0, "top")
    board.blitter.current_page.set(0, 1, "mid")
    board.blitter.current_page.set(0, 2, "bot")

    board.cursor.set_position(0, 2)
    board.cursor.line_feed()

    assert board.cursor.y == 2
    assert board.blitter.current_page.get_line_text(0).startswith("mid")
    assert board.blitter.current_page.get_line_text(1).startswith("bot")


def test_cursor_device_text_write_wrap_preparation():
    board = Board(width=4, height=3)
    cursor = board.cursor

    cursor.x = 4
    cursor.y = 0
    cursor.prepare_for_text_write()

    assert (cursor.x, cursor.y) == (0, 1)


def test_origin_mode_column_is_relative_to_left_margin():
    board = Board(width=20, height=10)
    board.parser.feed("\x1b[?69h")  # DECLRMM
    board.parser.feed("\x1b[5;15s")  # DECSLRM: margins at columns 5-15
    board.parser.feed("\x1b[?6h")  # DECOM

    board.parser.feed("\x1b[1;1H")  # home is the margin corner under origin mode
    assert board.cursor.x == 4

    board.parser.feed("\x1b[1;99H")  # clamped inside the right margin
    assert board.cursor.x == 14
