from bittty import Board
from bittty.parser import Parser
from bittty.style import parse_sgr_sequence


def test_write_cell_no_auto_wrap():
    terminal = Board(width=5, height=5)
    terminal.modes.auto_wrap = False
    terminal.cursor.x = 4
    terminal.cursor.y = 0
    terminal.blitter.write_text("a")
    assert terminal.cursor.x == 4
    terminal.blitter.write_text("b")
    assert terminal.cursor.x == 4
    assert terminal.blitter.current_buffer.get_line_text(0) == "    b"


def test_write_cell_clip_at_width():
    terminal = Board(width=5, height=5)
    terminal.modes.auto_wrap = False
    terminal.cursor.x = 5  # Set cursor beyond width
    terminal.cursor.y = 0
    terminal.blitter.write_text("X")
    assert terminal.cursor.x == 4  # Should be clamped to width - 1
    assert terminal.blitter.current_buffer.get_line_text(0) == "    X"


def test_write_cell_overwrite_at_end_of_line():
    terminal = Board(width=10, height=5)
    terminal.blitter.current_buffer.set(0, 0, "abc")
    terminal.cursor.x = 3
    terminal.cursor.y = 0
    terminal.blitter.write_text("X")
    assert terminal.blitter.current_buffer.get_line_text(0) == "abcX      "


def test_write_cell_overwrite_empty_line():
    terminal = Board(width=10, height=5)
    terminal.cursor.x = 0
    terminal.cursor.y = 0
    terminal.blitter.write_text("A")
    assert terminal.blitter.current_buffer.get_line_text(0) == "A         "


def test_write_cell_overwrite_with_style():
    terminal = Board(width=10, height=5)
    parser = Parser(terminal)
    terminal.blitter.current_buffer.set(0, 0, "12345")
    terminal.cursor.x = 2
    terminal.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_with_style():
    terminal = Board(width=10, height=5)
    parser = Parser(terminal)
    terminal.modes.insert_mode = True
    terminal.blitter.current_buffer.set(0, 0, "12345")
    terminal.cursor.x = 2
    terminal.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "12X345    "
    assert terminal.blitter.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_at_end_of_line():
    terminal = Board(width=10, height=5)
    parser = Parser(terminal)
    terminal.modes.insert_mode = True
    terminal.blitter.current_buffer.set(0, 0, "123")
    terminal.cursor.x = 5
    terminal.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "123  X    "
    assert terminal.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_at_start_of_line():
    terminal = Board(width=10, height=5)
    parser = Parser(terminal)
    terminal.blitter.current_buffer.set(0, 0, "12345")
    terminal.cursor.x = 0
    terminal.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "X2345     "
    assert terminal.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_and_truncate():
    terminal = Board(width=5, height=5)
    parser = Parser(terminal)
    terminal.modes.insert_mode = True
    terminal.blitter.current_buffer.set(0, 0, "12345")
    terminal.cursor.x = 2
    terminal.cursor.y = 0
    parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "12X34"
    assert terminal.blitter.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_at_start_of_line_with_style():
    terminal = Board(width=10, height=5)
    terminal.blitter.current_buffer.set(0, 0, "12345")
    terminal.cursor.x = 0
    terminal.cursor.y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "X2345     "
    assert terminal.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_middle_of_line_with_style():
    terminal = Board(width=10, height=5)
    terminal.blitter.current_buffer.set(0, 0, "0123456789")
    terminal.cursor.x = 5
    terminal.cursor.y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "01234X6789"
    assert terminal.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_middle_of_line_with_style():
    terminal = Board(width=10, height=5)
    terminal.modes.insert_mode = True
    terminal.blitter.current_buffer.set(0, 0, "0123456789")
    terminal.cursor.x = 5
    terminal.cursor.y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "01234X5678"
    assert terminal.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_at_start_of_line_with_style():
    terminal = Board(width=10, height=5)
    terminal.modes.insert_mode = True
    terminal.blitter.current_buffer.set(0, 0, "0123456789")
    terminal.cursor.x = 0
    terminal.cursor.y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "X012345678"
    assert terminal.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_at_end_of_line_with_style():
    terminal = Board(width=10, height=5)
    terminal.modes.insert_mode = True
    terminal.blitter.current_buffer.set(0, 0, "012345678")
    terminal.cursor.x = 9
    terminal.cursor.y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "012345678X"
    assert terminal.blitter.current_buffer.get_cell(9, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_into_empty_line_with_style():
    terminal = Board(width=10, height=5)
    terminal.modes.insert_mode = True
    terminal.cursor.x = 0
    terminal.cursor.y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "X         "
    assert terminal.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_into_empty_line_with_style():
    terminal = Board(width=10, height=5)
    terminal.cursor.x = 0
    terminal.cursor.y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "X         "
    assert terminal.blitter.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_beyond_end_of_line_with_style():
    terminal = Board(width=10, height=5)
    terminal.blitter.current_buffer.set(0, 0, "abc")
    terminal.cursor.x = 5
    terminal.cursor.y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "abc  X    "
    assert terminal.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_beyond_end_of_line_with_style():
    terminal = Board(width=10, height=5)
    terminal.modes.insert_mode = True
    terminal.blitter.current_buffer.set(0, 0, "abc")
    terminal.cursor.x = 5
    terminal.cursor.y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.blitter.current_buffer.get_line_text(0) == "abc  X    "
    assert terminal.blitter.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_invalid_cursor():
    terminal = Board(width=10, height=5)
    terminal.cursor.y = 10  # Invalid cursor position
    terminal.blitter.write_text("a")
    # Should not raise an error and do nothing


def test_long_print_run_wraps_across_lines():
    """A single PRINT run longer than the width wraps instead of truncating."""
    terminal = Board(width=10, height=5)
    terminal.parser.feed("A" * 25)

    buffer = terminal.blitter.current_buffer
    assert buffer.get_line_text(0) == "A" * 10
    assert buffer.get_line_text(1) == "A" * 10
    assert buffer.get_line_text(2) == "A" * 5 + " " * 5
    assert terminal.cursor.y == 2
    assert terminal.cursor.x == 5


def test_long_print_run_scrolls_at_the_bottom():
    """Wrapping a long run on the last line scrolls the screen."""
    terminal = Board(width=10, height=3)
    terminal.cursor.y = 2
    terminal.parser.feed("B" * 15)

    buffer = terminal.blitter.current_buffer
    assert buffer.get_line_text(1) == "B" * 10
    assert buffer.get_line_text(2) == "B" * 5 + " " * 5
    assert terminal.cursor.y == 2


def test_long_print_run_without_autowrap_clips_to_last_column():
    """With autowrap off, overflow collapses into the last column (last char wins)."""
    terminal = Board(width=5, height=3)
    terminal.modes.auto_wrap = False
    terminal.parser.feed("abcdefgh")

    buffer = terminal.blitter.current_buffer
    assert buffer.get_line_text(0) == "abcdh"
    assert buffer.get_line_text(1).strip() == ""
    assert terminal.cursor.x == 4
