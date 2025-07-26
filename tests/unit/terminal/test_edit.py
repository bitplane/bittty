from bittty.terminal import Terminal
from bittty import constants
from bittty.parser import Parser
from bittty.style import Style, parse_sgr_sequence


def test_write_cell_overwrite():
    terminal = Terminal(width=10, height=1)
    parser = Parser(terminal)
    parser = Parser(terminal)
    parser.feed("\x1b[31m")  # Set red color
    parser.feed("A")
    assert terminal.current_buffer.get_line_text(0) == "A         "
    assert terminal.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[31m"), "A")
    assert terminal.cursor_x == 1

    parser.feed("\x1b[32m")  # Set green color
    parser.feed("B")
    assert terminal.current_buffer.get_line_text(0) == "AB        "
    assert terminal.current_buffer.get_cell(1, 0) == (parse_sgr_sequence("\x1b[32m"), "B")
    assert terminal.cursor_x == 2

    terminal.set_cursor(0, 0)
    parser.feed("\x1b[34m")  # Set blue color
    parser.feed("C")
    assert terminal.current_buffer.get_line_text(0) == "CB        "
    assert terminal.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[34m"), "C")
    assert terminal.cursor_x == 1


def test_write_cell_insert_mode():
    terminal = Terminal(width=10, height=1)
    parser = Parser(terminal)
    parser = Parser(terminal)
    parser.feed("\x1b[31m")  # Set red color
    parser.feed("A")
    parser.feed("\x1b[32m")  # Set green color
    parser.feed("B")
    terminal.set_cursor(0, 0)
    terminal.insert_mode = True
    parser.feed("\x1b[34m")  # Set blue color
    parser.feed("C")
    assert terminal.current_buffer.get_line_text(0) == "CAB       "
    assert terminal.current_buffer.get_cell(0, 0) == (parse_sgr_sequence("\x1b[34m"), "C")
    assert terminal.current_buffer.get_cell(1, 0) == (parse_sgr_sequence("\x1b[31m"), "A")
    assert terminal.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[32m"), "B")
    assert terminal.cursor_x == 1


def test_write_cell_autowrap():
    terminal = Terminal(width=3, height=2)
    parser = Parser(terminal)
    parser.feed("\x1b[31m")  # Set red color
    parser.feed("A")
    parser.feed("\x1b[32m")  # Set green color
    parser.feed("B")
    parser.feed("\x1b[34m")  # Set blue color
    parser.feed("C")
    assert terminal.current_buffer.get_line_text(0) == "ABC"
    assert terminal.cursor_x == 3
    assert terminal.cursor_y == 0

    parser.feed("\x1b[33m")  # Set yellow color
    parser.feed("D")  # Should wrap
    assert terminal.current_buffer.get_line_text(1) == "D  "
    assert terminal.cursor_x == 1
    assert terminal.cursor_y == 1


def test_clear_rect():
    terminal = Terminal(width=5, height=5)
    for y in range(5):
        for x in range(5):
            terminal.current_buffer.set_cell(x, y, "X", "\x1b[31m")

    terminal.clear_rect(1, 1, 3, 3)

    for y in range(5):
        for x in range(5):
            if 1 <= x <= 3 and 1 <= y <= 3:
                assert terminal.current_buffer.get_cell(x, y) == (Style(), " ")
            else:
                assert terminal.current_buffer.get_cell(x, y) == (parse_sgr_sequence("\x1b[31m"), "X")


def test_clear_screen():
    terminal = Terminal(width=10, height=5)
    for y in range(5):
        for x in range(10):
            terminal.current_buffer.set_cell(x, y, chr(ord("A") + y))

    terminal.set_cursor(5, 2)

    # Mode 0: Clear from cursor to end of terminal
    terminal.clear_screen(constants.ERASE_FROM_CURSOR_TO_END)
    assert terminal.current_buffer.get_line_text(0) == "AAAAAAAAAA"
    assert terminal.current_buffer.get_line_text(1) == "BBBBBBBBBB"
    assert terminal.current_buffer.get_line_text(2) == "CCCCC     "
    assert terminal.current_buffer.get_line_text(3) == "          "
    assert terminal.current_buffer.get_line_text(4) == "          "

    # Reset terminal
    for y in range(5):
        for x in range(10):
            terminal.current_buffer.set_cell(x, y, chr(ord("A") + y))
    terminal.set_cursor(5, 2)

    # Mode 1: Clear from beginning of terminal to cursor
    terminal.clear_screen(constants.ERASE_FROM_START_TO_CURSOR)
    assert terminal.current_buffer.get_line_text(0) == "          "
    assert terminal.current_buffer.get_line_text(1) == "          "
    assert terminal.current_buffer.get_line_text(2) == "      CCCC"
    assert terminal.current_buffer.get_line_text(3) == "DDDDDDDDDD"
    assert terminal.current_buffer.get_line_text(4) == "EEEEEEEEEE"

    # Reset terminal
    for y in range(5):
        for x in range(10):
            terminal.current_buffer.set_cell(x, y, chr(ord("A") + y))
    terminal.set_cursor(5, 2)

    # Mode 2: Clear entire terminal
    terminal.clear_screen(constants.ERASE_ALL)
    for y in range(5):
        assert terminal.current_buffer.get_line_text(y) == "          "


def test_clear_line():
    terminal = Terminal(width=10, height=1)
    for x in range(10):
        terminal.current_buffer.set_cell(x, 0, "X")
    terminal.set_cursor(5, 0)

    # Mode 0: Clear from cursor to end of line
    terminal.clear_line(constants.ERASE_FROM_CURSOR_TO_END)
    assert terminal.current_buffer.get_line_text(0) == "XXXXX     "

    # Reset
    for x in range(10):
        terminal.current_buffer.set_cell(x, 0, "X")
    terminal.set_cursor(5, 0)

    # Mode 1: Clear from beginning of line to cursor
    terminal.clear_line(constants.ERASE_FROM_START_TO_CURSOR)
    assert terminal.current_buffer.get_line_text(0) == "      XXXX"

    # Reset
    for x in range(10):
        terminal.current_buffer.set_cell(x, 0, "X")
    terminal.set_cursor(5, 0)

    # Mode 2: Clear entire line
    terminal.clear_line(constants.ERASE_ALL)
    assert terminal.current_buffer.get_line_text(0) == "          "


def test_insert_lines():
    terminal = Terminal(width=10, height=5)
    for y in range(5):
        terminal.current_buffer.set(0, y, f"Line {y}")
    terminal.set_cursor(0, 2)

    terminal.insert_lines(1)
    assert terminal.current_buffer.get_line_text(0) == "Line 0    "
    assert terminal.current_buffer.get_line_text(1) == "Line 1    "
    assert terminal.current_buffer.get_line_text(2) == "          "
    assert terminal.current_buffer.get_line_text(3) == "Line 2    "
    assert terminal.current_buffer.get_line_text(4) == "Line 3    "

    # Insert multiple lines
    terminal = Terminal(width=10, height=5)
    for y in range(5):
        terminal.current_buffer.set(0, y, f"Line {y}")
    terminal.set_cursor(0, 1)
    terminal.insert_lines(2)
    assert terminal.current_buffer.get_line_text(0) == "Line 0    "
    assert terminal.current_buffer.get_line_text(1) == "          "
    assert terminal.current_buffer.get_line_text(2) == "          "
    assert terminal.current_buffer.get_line_text(3) == "Line 1    "
    assert terminal.current_buffer.get_line_text(4) == "Line 2    "


def test_delete_lines():
    terminal = Terminal(width=10, height=5)
    for y in range(5):
        terminal.current_buffer.set(0, y, f"Line {y}")
    terminal.set_cursor(0, 1)

    terminal.delete_lines(1)
    assert terminal.current_buffer.get_line_text(0) == "Line 0    "
    assert terminal.current_buffer.get_line_text(1) == "Line 2    "
    assert terminal.current_buffer.get_line_text(2) == "Line 3    "
    assert terminal.current_buffer.get_line_text(3) == "Line 4    "
    assert terminal.current_buffer.get_line_text(4) == "          "

    # Delete multiple lines
    terminal = Terminal(width=10, height=5)
    for y in range(5):
        terminal.current_buffer.set(0, y, f"Line {y}")
    terminal.set_cursor(0, 0)
    terminal.delete_lines(2)
    assert terminal.current_buffer.get_line_text(0) == "Line 2    "
    assert terminal.current_buffer.get_line_text(1) == "Line 3    "
    assert terminal.current_buffer.get_line_text(2) == "Line 4    "
    assert terminal.current_buffer.get_line_text(3) == "          "
    assert terminal.current_buffer.get_line_text(4) == "          "


def test_insert_characters():
    terminal = Terminal(width=10, height=1)
    terminal.current_buffer.set(0, 0, "ABCDEFGHIJ")
    terminal.set_cursor(2, 0)

    terminal.insert_characters(3)
    assert terminal.current_buffer.get_line_text(0) == "AB   CDEFG"


def test_delete_characters():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "12345")
    terminal.cursor_x = 2
    terminal.cursor_y = 0
    terminal.delete_characters(2)
    assert terminal.current_buffer.get_line_text(0) == "125       "


def test_delete_characters_from_middle_of_line():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "123456789")
    terminal.cursor_x = 2
    terminal.cursor_y = 0
    terminal.delete_characters(3)
    assert terminal.current_buffer.get_line_text(0) == "126789    "


def test_delete_characters_at_end_of_line_no_effect():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "abc")
    terminal.cursor_x = 3
    terminal.cursor_y = 0
    terminal.delete_characters(1)
    assert terminal.current_buffer.get_line_text(0) == "abc       "


def test_delete_characters_beyond_end_of_line():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "12345")
    terminal.cursor_x = 2
    terminal.cursor_y = 0
    terminal.delete_characters(10)  # Attempt to delete more than available
    assert terminal.current_buffer.get_line_text(0) == "12        "


def test_delete_characters_from_empty_line():
    terminal = Terminal(width=10, height=5)
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.delete_characters(5)
    assert terminal.current_buffer.get_line_text(0) == "          "


def test_delete_last_character_on_line():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "abcde")
    terminal.cursor_x = 4
    terminal.cursor_y = 0
    terminal.delete_characters(1)
    assert terminal.current_buffer.get_line_text(0) == "abcd      "


def test_insert_characters_at_end_of_line():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "12345")
    terminal.cursor_x = 5
    terminal.cursor_y = 0
    terminal.insert_characters(2)
    assert terminal.current_buffer.get_line_text(0) == "12345     "


def test_insert_characters_invalid_cursor():
    terminal = Terminal(width=10, height=5)
    terminal.cursor_y = 10  # Invalid cursor position
    terminal.insert_characters(1)
    # Should not raise an error and do nothing


def test_delete_characters_invalid_cursor():
    terminal = Terminal(width=10, height=5)
    terminal.cursor_y = 10  # Invalid cursor position
    terminal.delete_characters(1)
    # Should not raise an error and do nothing
