from bittty import Board, Parser
from bittty.operations import Operation
from bittty.style import parse_sgr_sequence


def test_board_exposes_device_slots():
    board = Board(width=12, height=4)

    assert board.parser.sink is board
    assert board.devices["cursor"] is board.cursor
    assert board.devices["host"] is board.host
    assert board.devices["blitter"] is board.blitter
    assert board.devices["style"] is board.style
    assert board.devices["title"] is board.title
    assert board.get_device("keyboard") is board.keyboard
    assert board.get_device("mouse") is board.mouse


def test_parser_attaches_to_a_board():
    board = Board(width=12, height=4)

    parser = Parser(board)

    assert parser.sink is board


def test_board_routes_operations_to_plugged_in_devices():
    board = Board(width=12, height=4)

    board.handle_operation(Operation("SGR", (parse_sgr_sequence("\x1b[31m"), False), "\x1b[31m"))
    board.handle_operation(Operation("PRINT", ("red",), "red"))
    board.handle_operation(Operation("CUP", (4, 1), "\x1b[2;5H"))
    board.handle_operation(Operation("SET_WINDOW_TITLE", ("Board",), "\x1b]2;Board\x07"))

    assert board.blitter.current_page.get_line_text(0).startswith("red")
    assert (board.cursor.x, board.cursor.y) == (4, 1)
    assert board.title.title == "Board"


def test_capture_text_returns_trimmed_plain_text():
    board = Board(width=8, height=5)
    page = board.blitter.current_page
    page.set(0, 0, "  hello")
    page.set(2, 2, "world")
    page.set(0, 3, "red", "\x1b[31m")

    assert board.capture_text() == "  hello\n\n  world\nred"
    assert "\x1b" not in board.capture_text()


def test_capture_text_can_preserve_the_exact_screen_rectangle():
    board = Board(width=5, height=3)
    board.blitter.current_page.set(0, 0, "hi")

    assert board.capture_text(trim=False) == "hi   \n     \n     "


def test_capture_text_returns_empty_string_for_a_blank_trimmed_screen():
    board = Board(width=5, height=3)

    assert board.capture_text() == ""


def test_capture_text_reads_the_active_screen():
    board = Board(width=8, height=2)
    board.blitter.current_page.set(0, 0, "primary")
    board.blitter.switch_screen(True)
    board.blitter.current_page.set(0, 0, "alternate")

    assert board.capture_text() == "alternat"

    board.blitter.switch_screen(False)
    assert board.capture_text() == "primary"
