from bittty.terminal import Terminal
from bittty.parser import Parser
from bittty.style import parse_sgr_sequence


def test_write_cell_no_auto_wrap():
    terminal = Terminal(width=5, height=5)
    terminal.auto_wrap = False
    terminal.cursor_x = 4
    terminal.cursor_y = 0
    terminal.write_text("a")
    assert terminal.cursor_x == 4
    terminal.write_text("b")
    assert terminal.cursor_x == 4
    assert terminal.current_buffer.get_line_text(0) == "    b"


def test_write_cell_clip_at_width():
    terminal = Terminal(width=5, height=5)
    terminal.auto_wrap = False
    terminal.cursor_x = 5  # Set cursor beyond width
    terminal.cursor_y = 0
    terminal.write_text("X")
    assert terminal.cursor_x == 4  # Should be clamped to width - 1
    assert terminal.current_buffer.get_line_text(0) == "    X"


def test_write_cell_overwrite_at_end_of_line():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "abc")
    terminal.cursor_x = 3
    terminal.cursor_y = 0
    terminal.write_text("X")
    assert terminal.current_buffer.get_line_text(0) == "abcX      "


def test_write_cell_overwrite_empty_line():
    terminal = Terminal(width=10, height=5)
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.write_text("A")
    assert terminal.current_buffer.get_line_text(0) == "A         "


def test_write_cell_overwrite_with_style():
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)
    terminal.current_buffer.set(0, 0, "12345")
    terminal.cursor_x = 2
    terminal.cursor_y = 0
    parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_with_style():
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)
    terminal.insert_mode = True
    terminal.current_buffer.set(0, 0, "12345")
    terminal.cursor_x = 2
    terminal.cursor_y = 0
    parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "12X345    "
    assert terminal.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_at_end_of_line():
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)
    terminal.insert_mode = True
    terminal.current_buffer.set(0, 0, "123")
    terminal.cursor_x = 5
    terminal.cursor_y = 0
    parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "123  X    "
    assert terminal.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_at_start_of_line():
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)
    terminal.current_buffer.set(0, 0, "12345")
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "X2345     "
    assert terminal.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_and_truncate():
    terminal = Terminal(width=5, height=5)
    parser = Parser(terminal)
    terminal.insert_mode = True
    terminal.current_buffer.set(0, 0, "12345")
    terminal.cursor_x = 2
    terminal.cursor_y = 0
    parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "12X34"
    assert terminal.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_at_start_of_line_with_style():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "12345")
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "X2345     "
    assert terminal.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_middle_of_line_with_style():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "0123456789")
    terminal.cursor_x = 5
    terminal.cursor_y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "01234X6789"
    assert terminal.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_middle_of_line_with_style():
    terminal = Terminal(width=10, height=5)
    terminal.insert_mode = True
    terminal.current_buffer.set(0, 0, "0123456789")
    terminal.cursor_x = 5
    terminal.cursor_y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "01234X5678"
    assert terminal.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_at_start_of_line_with_style():
    terminal = Terminal(width=10, height=5)
    terminal.insert_mode = True
    terminal.current_buffer.set(0, 0, "0123456789")
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "X012345678"
    assert terminal.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_at_end_of_line_with_style():
    terminal = Terminal(width=10, height=5)
    terminal.insert_mode = True
    terminal.current_buffer.set(0, 0, "012345678")
    terminal.cursor_x = 9
    terminal.cursor_y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "012345678X"
    assert terminal.current_buffer.get_cell(9, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_into_empty_line_with_style():
    terminal = Terminal(width=10, height=5)
    terminal.insert_mode = True
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "X         "
    assert terminal.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_into_empty_line_with_style():
    terminal = Terminal(width=10, height=5)
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "X         "
    assert terminal.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_overwrite_beyond_end_of_line_with_style():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "abc")
    terminal.cursor_x = 5
    terminal.cursor_y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "abc  X    "
    assert terminal.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_insert_beyond_end_of_line_with_style():
    terminal = Terminal(width=10, height=5)
    terminal.insert_mode = True
    terminal.current_buffer.set(0, 0, "abc")
    terminal.cursor_x = 5
    terminal.cursor_y = 0
    terminal.parser.feed("\x1b[31mX")
    assert terminal.current_buffer.get_line_text(0) == "abc  X    "
    assert terminal.current_buffer.get_cell(5, 0) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_write_cell_invalid_cursor():
    terminal = Terminal(width=10, height=5)
    terminal.cursor_y = 10  # Invalid cursor position
    terminal.write_text("a")
    # Should not raise an error and do nothing
