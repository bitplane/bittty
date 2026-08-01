from bittty import Board
from bittty.parser import Parser
from bittty.style import parse_sgr_sequence


def test_write_cell_no_auto_wrap():
    board = Board(width=5, height=5)
    board.modes.auto_wrap = False
    board.cursor.x = 4
    board.cursor.y = 0
    board.blitter.write_text("a")
    assert board.cursor.x == 4
    board.blitter.write_text("b")
    assert board.cursor.x == 4
    assert board.blitter.current_buffer.get_line_text(0) == "    b"


def test_write_cell_clip_at_width():
    board = Board(width=5, height=5)
    board.modes.auto_wrap = False
    board.cursor.x = 5  # Set cursor beyond width
    board.cursor.y = 0
    board.blitter.write_text("X")
    assert board.cursor.x == 4  # Should be clamped to width - 1
    assert board.blitter.current_buffer.get_line_text(0) == "    X"


def test_write_cell_overwrite_at_end_of_line():
    board = Board(width=10, height=5)
    board.blitter.current_buffer.set(0, 0, "abc")
    board.cursor.x = 3
    board.cursor.y = 0
    board.blitter.write_text("X")
    assert board.blitter.current_buffer.get_line_text(0) == "abcX      "


def test_write_cell_overwrite_empty_line():
    board = Board(width=10, height=5)
    board.cursor.x = 0
    board.cursor.y = 0
    board.blitter.write_text("A")
    assert board.blitter.current_buffer.get_line_text(0) == "A         "


def test_write_cell_overwrite_with_style():
    board = Board(width=10, height=5)
    parser = Parser(board)
    board.blitter.current_buffer.set(0, 0, "12345")
    board.cursor.x = 2
    board.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_with_style():
    board = Board(width=10, height=5)
    parser = Parser(board)
    board.modes.insert_mode = True
    board.blitter.current_buffer.set(0, 0, "12345")
    board.cursor.x = 2
    board.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "12X345    "
    assert board.blitter.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_at_end_of_line():
    board = Board(width=10, height=5)
    parser = Parser(board)
    board.modes.insert_mode = True
    board.blitter.current_buffer.set(0, 0, "123")
    board.cursor.x = 5
    board.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "123  X    "
    assert board.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_at_start_of_line():
    board = Board(width=10, height=5)
    parser = Parser(board)
    board.blitter.current_buffer.set(0, 0, "12345")
    board.cursor.x = 0
    board.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "X2345     "
    assert board.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_and_truncate():
    board = Board(width=5, height=5)
    parser = Parser(board)
    board.modes.insert_mode = True
    board.blitter.current_buffer.set(0, 0, "12345")
    board.cursor.x = 2
    board.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "12X34"
    assert board.blitter.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_at_start_of_line_with_style():
    board = Board(width=10, height=5)
    board.blitter.current_buffer.set(0, 0, "12345")
    board.cursor.x = 0
    board.cursor.y = 0
    board.parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "X2345     "
    assert board.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_middle_of_line_with_style():
    board = Board(width=10, height=5)
    board.blitter.current_buffer.set(0, 0, "0123456789")
    board.cursor.x = 5
    board.cursor.y = 0
    board.parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "01234X6789"
    assert board.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_middle_of_line_with_style():
    board = Board(width=10, height=5)
    board.modes.insert_mode = True
    board.blitter.current_buffer.set(0, 0, "0123456789")
    board.cursor.x = 5
    board.cursor.y = 0
    board.parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "01234X5678"
    assert board.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_at_start_of_line_with_style():
    board = Board(width=10, height=5)
    board.modes.insert_mode = True
    board.blitter.current_buffer.set(0, 0, "0123456789")
    board.cursor.x = 0
    board.cursor.y = 0
    board.parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "X012345678"
    assert board.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_at_end_of_line_with_style():
    board = Board(width=10, height=5)
    board.modes.insert_mode = True
    board.blitter.current_buffer.set(0, 0, "012345678")
    board.cursor.x = 9
    board.cursor.y = 0
    board.parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "012345678X"
    assert board.blitter.current_buffer.get_cell(9, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_into_empty_line_with_style():
    board = Board(width=10, height=5)
    board.modes.insert_mode = True
    board.cursor.x = 0
    board.cursor.y = 0
    board.parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "X         "
    assert board.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_into_empty_line_with_style():
    board = Board(width=10, height=5)
    board.cursor.x = 0
    board.cursor.y = 0
    board.parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "X         "
    assert board.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_beyond_end_of_line_with_style():
    board = Board(width=10, height=5)
    board.blitter.current_buffer.set(0, 0, "abc")
    board.cursor.x = 5
    board.cursor.y = 0
    board.parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "abc  X    "
    assert board.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_beyond_end_of_line_with_style():
    board = Board(width=10, height=5)
    board.modes.insert_mode = True
    board.blitter.current_buffer.set(0, 0, "abc")
    board.cursor.x = 5
    board.cursor.y = 0
    board.parser.feed("\x1b[31mX")
    assert board.blitter.current_buffer.get_line_text(0) == "abc  X    "
    assert board.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_long_print_run_wraps_across_lines():
    """A single PRINT run longer than the width wraps instead of truncating."""
    board = Board(width=10, height=5)
    board.parser.feed("A" * 25)

    buffer = board.blitter.current_buffer
    assert buffer.get_line_text(0) == "A" * 10
    assert buffer.get_line_text(1) == "A" * 10
    assert buffer.get_line_text(2) == "A" * 5 + " " * 5
    assert board.cursor.y == 2
    assert board.cursor.x == 5


def test_long_print_run_scrolls_at_the_bottom():
    """Wrapping a long run on the last line scrolls the screen."""
    board = Board(width=10, height=3)
    board.cursor.y = 2
    board.parser.feed("B" * 15)

    buffer = board.blitter.current_buffer
    assert buffer.get_line_text(1) == "B" * 10
    assert buffer.get_line_text(2) == "B" * 5 + " " * 5
    assert board.cursor.y == 2


def test_long_print_run_without_autowrap_clips_to_last_column():
    """With autowrap off, overflow collapses into the last column (last char wins)."""
    board = Board(width=5, height=3)
    board.modes.auto_wrap = False
    board.parser.feed("abcdefgh")

    buffer = board.blitter.current_buffer
    assert buffer.get_line_text(0) == "abcdh"
    assert buffer.get_line_text(1).strip() == ""
    assert board.cursor.x == 4
