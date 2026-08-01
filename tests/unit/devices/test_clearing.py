from bittty import Board
from bittty.constants import (
    ERASE_ALL,
    ERASE_FROM_CURSOR_TO_END,
    ERASE_FROM_START_TO_CURSOR,
)


def test_clear_rect():
    board = Board(width=10, height=5)
    for y in range(5):
        for x in range(10):
            board.blitter.current_buffer.set_cell(x, y, "X")

    board.blitter.clear_rect(2, 1, 5, 3)
    from bittty.style import Style

    for y in range(5):
        for x in range(10):
            if 1 <= y <= 3 and 2 <= x <= 5:
                assert board.blitter.current_buffer.get_cell(x, y) == (Style(), " ")
            else:
                assert board.blitter.current_buffer.get_cell(x, y) == (Style(), "X")


def test_clear_rect_with_style():
    board = Board(width=10, height=5)
    for y in range(5):
        for x in range(10):
            board.blitter.current_buffer.set_cell(x, y, "X", f"\x1b[{31 + y}m")

    board.blitter.clear_rect(2, 1, 5, 3, "\x1b[33m")
    from bittty.style import parse_sgr_sequence

    yellow_style = parse_sgr_sequence("\x1b[33m")
    for y in range(5):
        for x in range(10):
            if 1 <= y <= 3 and 2 <= x <= 5:
                assert board.blitter.current_buffer.get_cell(x, y) == (yellow_style, " ")
            else:
                expected_style = parse_sgr_sequence(f"\x1b[{31 + y}m")
                assert board.blitter.current_buffer.get_cell(x, y) == (expected_style, "X")


def test_clear_line_from_cursor_to_end():
    board = Board(width=10, height=5)
    board.blitter.current_buffer.set(0, 0, "0123456789")
    board.cursor.x = 5
    board.cursor.y = 0
    board.blitter.clear_line(ERASE_FROM_CURSOR_TO_END)
    assert board.blitter.current_buffer.get_line_text(0) == "01234     "


def test_clear_line_from_beginning_to_cursor():
    board = Board(width=10, height=5)
    board.blitter.current_buffer.set(0, 0, "0123456789")
    board.cursor.x = 5
    board.cursor.y = 0
    board.blitter.clear_line(ERASE_FROM_START_TO_CURSOR)
    assert board.blitter.current_buffer.get_line_text(0) == "      6789"


def test_clear_line_entire_line():
    board = Board(width=10, height=5)
    board.blitter.current_buffer.set(0, 0, "0123456789")
    board.cursor.y = 0
    board.blitter.clear_line(ERASE_ALL)
    assert board.blitter.current_buffer.get_line_text(0) == "          "


def test_clear_line_with_mixed_styles():
    board = Board(width=10, height=5)
    board.blitter.current_buffer.set(0, 0, "ABCDEFGHI")
    board.cursor.x = 3
    board.cursor.y = 0
    board.blitter.clear_line(0)  # Clear from cursor to end
    assert board.blitter.current_buffer.get_line_text(0) == "ABC       "

    board.blitter.current_buffer.set(0, 1, "ABCDEFGHI")
    board.cursor.x = 3
    board.cursor.y = 1
    board.blitter.clear_line(1)  # Clear from beginning to cursor
    assert board.blitter.current_buffer.get_line_text(1) == "    EFGHI "
