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

    assert board.blitter.current_buffer.get_line_text(0).startswith("red")
    assert (board.cursor.x, board.cursor.y) == (4, 1)
    assert board.title.title == "Board"
