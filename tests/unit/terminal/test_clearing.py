from bittty.terminal import Terminal
from bittty.constants import (
    ERASE_FROM_CURSOR_TO_END,
    ERASE_FROM_START_TO_CURSOR,
    ERASE_ALL,
)


def test_clear_rect():
    terminal = Terminal(width=10, height=5)
    for y in range(5):
        for x in range(10):
            terminal.current_buffer.set_cell(x, y, "X")

    terminal.clear_rect(2, 1, 5, 3)
    for y in range(5):
        for x in range(10):
            if 1 <= y <= 3 and 2 <= x <= 5:
                assert terminal.current_buffer.get_cell(x, y) == ("", " ")
            else:
                assert terminal.current_buffer.get_cell(x, y) == ("", "X")


def test_clear_rect_with_style():
    terminal = Terminal(width=10, height=5)
    for y in range(5):
        for x in range(10):
            terminal.current_buffer.set_cell(x, y, "X", f"\x1b[{31+y}m")

    terminal.clear_rect(2, 1, 5, 3, "\x1b[33m")
    for y in range(5):
        for x in range(10):
            if 1 <= y <= 3 and 2 <= x <= 5:
                assert terminal.current_buffer.get_cell(x, y) == ("\x1b[33m", " ")
            else:
                assert terminal.current_buffer.get_cell(x, y) == (f"\x1b[{31+y}m", "X")


def test_clear_line_from_cursor_to_end():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "0123456789")
    terminal.cursor_x = 5
    terminal.cursor_y = 0
    terminal.clear_line(ERASE_FROM_CURSOR_TO_END)
    assert terminal.current_buffer.get_line_text(0) == "01234     "


def test_clear_line_from_beginning_to_cursor():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "0123456789")
    terminal.cursor_x = 5
    terminal.cursor_y = 0
    terminal.clear_line(ERASE_FROM_START_TO_CURSOR)
    assert terminal.current_buffer.get_line_text(0) == "      6789"


def test_clear_line_entire_line():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "0123456789")
    terminal.cursor_y = 0
    terminal.clear_line(ERASE_ALL)
    assert terminal.current_buffer.get_line_text(0) == "          "


def test_clear_line_with_mixed_styles():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "ABCDEFGHI")
    terminal.cursor_x = 3
    terminal.cursor_y = 0
    terminal.clear_line(0)  # Clear from cursor to end
    assert terminal.current_buffer.get_line_text(0) == "ABC       "

    terminal.current_buffer.set(0, 1, "ABCDEFGHI")
    terminal.cursor_x = 3
    terminal.cursor_y = 1
    terminal.clear_line(1)  # Clear from beginning to cursor
    assert terminal.current_buffer.get_line_text(1) == "    EFGHI "


def test_clear_line_invalid_cursor():
    terminal = Terminal(width=10, height=5)
    terminal.cursor_y = 10  # Invalid cursor position
    terminal.clear_line(ERASE_FROM_CURSOR_TO_END)
    # Should not raise an error and do nothing


def test_clear_screen_invalid_cursor():
    terminal = Terminal(width=10, height=5)
    terminal.cursor_y = 10  # Invalid cursor position
    terminal.clear_screen(0)
    # Should not raise an error but still clear the terminal below
    assert all(c == " " for c in terminal.current_buffer.get_line_text(4))
