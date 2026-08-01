from bittty import constants
from bittty.operations import Operation
from bittty.style import parse_sgr_sequence
from bittty import Board


def test_screen_device_owns_pages_and_switches_the_active_one():
    board = Board(width=10, height=4)
    screen = board.blitter

    screen.current_page.set(0, 0, "primary")
    screen.switch_screen(True)
    screen.current_page.set(0, 0, "alt")

    assert screen.in_alt_screen is True
    assert screen.current_page is screen.alt_page
    assert screen.current_page.get_line_text(0).startswith("alt")

    screen.switch_screen(False)
    assert screen.current_page is screen.primary_page
    assert screen.current_page.get_line_text(0).startswith("primary")


def test_screen_device_write_text_uses_style_charset_and_insert_mode():
    board = Board(width=8, height=3)
    board.style.current_ansi_code = "\x1b[31m"
    board.modes.insert_mode = True
    board.blitter.current_page.set(0, 0, "abcd")
    board.cursor.set_position(2, 0)

    board.blitter.write_text("X")

    assert board.blitter.current_page.get_line_text(0) == "abXcd   "
    assert board.blitter.current_page.get_cell(2, 0) == (parse_sgr_sequence("\x1b[31m"), "X")
    assert board.cursor.x == 3
    assert board.blitter.last_printed_char == "X"


def test_screen_device_clear_uses_active_background_style():
    board = Board(width=6, height=2)
    board.style.current_ansi_code = "\x1b[42m"
    board.blitter.current_page.set(0, 0, "hello")
    board.cursor.set_position(1, 0)

    board.blitter.clear_line(constants.ERASE_FROM_CURSOR_TO_END)

    assert board.blitter.current_page.get_cell(0, 0)[1] == "h"
    assert board.blitter.current_page.get_cell(1, 0) == (parse_sgr_sequence("\x1b[42m"), " ")


def test_screen_device_scroll_region_and_line_operations():
    board = Board(width=8, height=4)
    screen = board.blitter
    for y in range(4):
        screen.current_page.set(0, y, f"line{y}")

    screen.set_scroll_region(1, 2)
    board.cursor.set_position(0, 1)
    screen.delete_lines(1)

    assert screen.current_page.get_line_text(1).startswith("line2")
    assert screen.current_page.get_line_text(2).strip() == ""


def test_screen_device_insert_and_delete_characters():
    board = Board(width=10, height=2)
    screen = board.blitter

    screen.current_page.set(0, 0, "ABCDEFGHIJ")
    board.cursor.set_position(2, 0)
    screen.insert_characters(3)
    assert screen.current_page.get_line_text(0) == "AB   CDEFG"

    board.cursor.set_position(2, 0)
    screen.delete_characters(4)
    assert screen.current_page.get_line_text(0) == "ABDEFG    "


def test_screen_device_edit_operations_are_operation_driven():
    board = Board(width=8, height=3)
    screen = board.blitter
    screen.current_page.set(0, 0, "abcdef")
    board.cursor.set_position(2, 0)

    screen.handle_operation(Operation("DCH", (2,), "\x1b[2P"))
    assert screen.current_page.get_line_text(0).startswith("abef")

    screen.last_printed_char = "X"
    screen.handle_operation(Operation("REP", (3,), "\x1b[3b"))
    assert screen.current_page.get_line_text(0).startswith("abXXX")
