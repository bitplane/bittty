from bittty import constants
from bittty.operations import Operation
from bittty.style import parse_sgr_sequence
from bittty import Board


def test_screen_device_owns_buffers_and_switches_active_buffer():
    terminal = Board(width=10, height=4)
    screen = terminal.board.screen

    screen.current_buffer.set(0, 0, "primary")
    screen.switch_screen(True)
    screen.current_buffer.set(0, 0, "alt")

    assert screen.in_alt_screen is True
    assert screen.current_buffer is screen.alt_buffer
    assert screen.current_buffer.get_line_text(0).startswith("alt")

    screen.switch_screen(False)
    assert screen.current_buffer is screen.primary_buffer
    assert screen.current_buffer.get_line_text(0).startswith("primary")


def test_screen_device_write_text_uses_style_charset_and_insert_mode():
    terminal = Board(width=8, height=3)
    terminal.board.style.current_ansi_code = "\x1b[31m"
    terminal.board.modes.insert_mode = True
    terminal.board.screen.current_buffer.set(0, 0, "abcd")
    terminal.board.cursor.set_position(2, 0)

    terminal.board.screen.write_text("X")

    assert terminal.board.screen.current_buffer.get_line_text(0) == "abXcd   "
    assert terminal.board.screen.current_buffer.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")
    assert terminal.board.cursor.x == 3
    assert terminal.board.screen.last_printed_char == "X"


def test_screen_device_clear_uses_active_background_style():
    terminal = Board(width=6, height=2)
    terminal.board.style.current_ansi_code = "\x1b[42m"
    terminal.board.screen.current_buffer.set(0, 0, "hello")
    terminal.board.cursor.set_position(1, 0)

    terminal.board.screen.clear_line(constants.ERASE_FROM_CURSOR_TO_END)

    assert terminal.board.screen.current_buffer.get_cell(0, 0)[1] == "h"
    assert terminal.board.screen.current_buffer.get_cell(1, 0) == (parse_sgr_sequence("\x1b[42m"), " ")


def test_screen_device_scroll_region_and_line_operations():
    terminal = Board(width=8, height=4)
    screen = terminal.board.screen
    for y in range(4):
        screen.current_buffer.set(0, y, f"line{y}")

    screen.set_scroll_region(1, 2)
    terminal.board.cursor.set_position(0, 1)
    screen.delete_lines(1)

    assert screen.current_buffer.get_line_text(1).startswith("line2")
    assert screen.current_buffer.get_line_text(2).strip() == ""


def test_screen_device_insert_and_delete_characters():
    terminal = Board(width=10, height=2)
    screen = terminal.board.screen

    screen.current_buffer.set(0, 0, "ABCDEFGHIJ")
    terminal.board.cursor.set_position(2, 0)
    screen.insert_characters(3)
    assert screen.current_buffer.get_line_text(0) == "AB   CDEFG"

    terminal.board.cursor.set_position(2, 0)
    screen.delete_characters(4)
    assert screen.current_buffer.get_line_text(0) == "ABDEFG    "


def test_screen_device_edit_operations_are_operation_driven():
    terminal = Board(width=8, height=3)
    screen = terminal.board.screen
    screen.current_buffer.set(0, 0, "abcdef")
    terminal.board.cursor.set_position(2, 0)

    screen.handle_operation(Operation("DCH", (2,), "\x1b[2P"))
    assert screen.current_buffer.get_line_text(0).startswith("abef")

    screen.last_printed_char = "X"
    screen.handle_operation(Operation("REP", (3,), "\x1b[3b"))
    assert screen.current_buffer.get_line_text(0).startswith("abXXX")
