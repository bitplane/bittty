"""Boundary semantics for DECLRMM and the DECSLRM scrolling rectangle."""

from bittty import Board, MemoryConnection, constants


def _board(width=10, height=4, left=3, right=7):
    board = Board(width=width, height=height)
    board.parser.feed(f"\x1b[?69h\x1b[{left};{right}s")
    return board


def _lines(board):
    return [board.blitter.current_buffer.get_line_text(y) for y in range(board.height)]


def test_invalid_decslrm_is_ignored_without_homing_cursor():
    board = _board()
    board.cursor.set_position(8, 2)

    board.parser.feed("\x1b[8;4s")

    assert (board.blitter.left_margin, board.blitter.right_margin) == (2, 6)
    assert (board.cursor.x, board.cursor.y) == (8, 2)


def test_decslrm_requires_at_least_two_columns():
    board = _board()
    board.cursor.set_position(8, 2)

    board.parser.feed("\x1b[5;5s")

    assert (board.blitter.left_margin, board.blitter.right_margin) == (2, 6)
    assert (board.cursor.x, board.cursor.y) == (8, 2)


def test_carriage_return_tab_and_backspace_use_horizontal_margins():
    board = _board()
    board.cursor.set_position(5, 1)
    board.cursor.carriage_return()
    assert board.cursor.x == 2

    board.cursor.horizontal_tab()
    assert board.cursor.x == 6

    board.cursor.backspace()
    assert board.cursor.x == 5
    board.cursor.set_position(2, 1)
    board.cursor.backspace()
    assert (board.cursor.x, board.cursor.y) == (2, 1)


def test_tabs_do_not_move_back_into_margins_when_cursor_is_outside_them():
    board = _board(width=12, left=3, right=7)

    board.cursor.set_position(9, 1)
    board.cursor.horizontal_tab()
    assert board.cursor.x == 11

    board.cursor.set_position(1, 1)
    board.cursor.backward_tab(1)
    assert board.cursor.x == 0


def test_ascii_text_wraps_from_right_to_left_margin():
    board = _board()
    board.cursor.set_position(2, 0)

    board.parser.feed("ABCDEf")

    assert _lines(board)[:2] == ["  ABCDE   ", "  f       "]
    assert (board.cursor.x, board.cursor.y) == (3, 1)


def test_inner_delayed_wrap_reports_the_right_margin_and_cursor_motion_cancels_it():
    board = _board()
    transport = MemoryConnection()
    board.host.attach(transport)
    board.cursor.set_position(2, 0)
    board.parser.feed("ABCDE")

    board.parser.feed("\x1b[6n")
    assert transport.data[-1] == "\x1b[1;7R"

    board.parser.feed("\x1b[DZ")
    assert _lines(board)[0] == "  ABCZE   "
    assert (board.cursor.x, board.cursor.y) == (6, 0)


def test_editing_at_delayed_wrap_uses_the_physical_right_margin_cell():
    board = _board()
    board.cursor.set_position(2, 0)
    board.parser.feed("ABCDE")

    board.parser.feed("\x1b[1X")

    assert _lines(board)[0] == "  ABCD    "
    assert (board.cursor.x, board.cursor.y) == (6, 0)
    board.parser.feed("Z")
    assert _lines(board)[0] == "  ABCDZ   "


def test_saving_at_delayed_wrap_saves_the_physical_cursor_position():
    board = _board()
    board.cursor.set_position(2, 0)
    board.parser.feed("ABCDE")

    board.cursor.save()
    board.cursor.set_position(0, 2)
    board.cursor.restore()
    board.parser.feed("Z")

    assert _lines(board)[0] == "  ABCDZ   "
    assert (board.cursor.display_x, board.cursor.y) == (6, 0)


def test_margin_wrap_scrolls_only_the_scrolling_rectangle():
    board = _board(height=3)
    for y, text in enumerate(("0000000000", "1111111111", "2222222222")):
        board.blitter.current_buffer.set(0, y, text)
    board.cursor.set_position(2, 2)

    board.parser.feed("ABCDEf")

    assert _lines(board) == [
        "0011111000",
        "11ABCDE111",
        "22f    222",
    ]
    assert (board.cursor.x, board.cursor.y) == (3, 2)


def test_wide_glyph_wraps_whole_at_the_right_margin():
    board = _board(width=8, height=2, left=2, right=5)
    board.cursor.set_position(4, 0)

    board.parser.feed("❌")

    assert board.blitter.current_buffer.get_cell(1, 1)[1] == "❌"
    assert board.blitter.current_buffer.get_cell(2, 1)[1] == ""
    assert (board.cursor.x, board.cursor.y) == (3, 1)


def test_ich_and_dch_stop_at_right_margin_and_preserve_neighbours():
    board = _board(width=10, height=3)
    board.blitter.current_buffer.set(0, 1, "ABCDEFGHIJ")
    board.cursor.set_position(3, 1)

    board.parser.feed("\x1b[2@")
    assert _lines(board)[1] == "ABC  DEHIJ"

    board.parser.feed("\x1b[3P")
    assert _lines(board)[1] == "ABCE   HIJ"


def test_ich_and_dch_are_ignored_outside_scrolling_rectangle():
    board = _board(width=10, height=4)
    board.blitter.set_scroll_region(1, 2)
    for y in (0, 1):
        board.blitter.current_buffer.set(0, y, "ABCDEFGHIJ")

    board.cursor.set_position(3, 0)
    board.parser.feed("\x1b[2@")
    board.cursor.set_position(8, 1)
    board.parser.feed("\x1b[2P")

    assert _lines(board)[:2] == ["ABCDEFGHIJ", "ABCDEFGHIJ"]


def test_insert_mode_printing_stops_at_right_margin():
    board = _board(width=10, height=3)
    board.blitter.current_buffer.set(0, 1, "ABCDEFGHIJ")
    board.cursor.set_position(3, 1)
    board.parser.feed("\x1b[4hXY")

    assert _lines(board)[1] == "ABCXYDEHIJ"


def test_decbifi_shift_only_at_exact_margin_and_affect_every_row():
    board = _board(width=10, height=4)
    board.blitter.set_scroll_region(1, 2)
    for y in range(board.height):
        board.blitter.current_buffer.set(0, y, "ABCDEFGHIJ")

    board.cursor.set_position(7, 0)  # outside and right of the margin
    board.parser.feed("\x1b9")
    assert board.cursor.x == 8
    assert _lines(board) == ["ABCDEFGHIJ"] * 4

    board.cursor.set_position(6, 0)  # exactly at the right margin
    board.parser.feed("\x1b9")
    assert _lines(board) == ["ABDEFG HIJ"] * 4

    board.cursor.set_position(1, 0)  # outside and left of the margin
    board.parser.feed("\x1b6")
    assert board.cursor.x == 0

    board.cursor.set_position(2, 0)  # exactly at the left margin
    board.parser.feed("\x1b6")
    assert _lines(board) == ["AB DEFGHIJ"] * 4


def test_declrmm_forces_single_width_lines_and_blocks_line_attributes():
    board = Board(width=10, height=3)
    board.blitter.current_buffer.set_line_attribute(1, constants.LINE_DOUBLE_WIDTH)

    board.parser.feed("\x1b[?69h")
    assert board.blitter.current_buffer.get_line_attribute(1) == constants.LINE_SINGLE

    board.cursor.set_position(0, 1)
    board.parser.feed("\x1b#6")
    assert board.blitter.current_buffer.get_line_attribute(1) == constants.LINE_SINGLE
