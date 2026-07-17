from bittty import Board, Parser
from bittty.operations import Operation
from bittty.style import parse_sgr_sequence


def test_terminal_builds_board_and_exposes_device_slots():
    terminal = Board(width=12, height=4)

    assert isinstance(terminal.board, Board)
    assert terminal.parser.sink is terminal.board
    assert terminal.board.devices["cursor"] is terminal.board.cursor
    assert terminal.board.devices["host"] is terminal.board.host
    assert terminal.board.devices["screen"] is terminal.board.screen
    assert terminal.board.devices["style"] is terminal.board.style
    assert terminal.board.devices["title"] is terminal.board.title
    assert terminal.board.get_device("keyboard") is terminal.board.keyboard
    assert terminal.board.get_device("mouse") is terminal.board.mouse


def test_parser_reuses_existing_terminal_board_by_default():
    terminal = Board(width=12, height=4)

    parser = Parser(terminal.board)

    assert parser.sink is terminal.board
    assert terminal.board.cursor is terminal.board.cursor


def test_board_routes_operations_to_plugged_in_devices():
    terminal = Board(width=12, height=4)
    board = terminal.board

    board.handle_operation(Operation("SGR", (parse_sgr_sequence("\x1b[31m"), False), "\x1b[31m"))
    board.handle_operation(Operation("PRINT", ("red",), "red"))
    board.handle_operation(Operation("CUP", (4, 1), "\x1b[2;5H"))
    board.handle_operation(Operation("SET_WINDOW_TITLE", ("Board",), "\x1b]2;Board\x07"))

    assert terminal.board.screen.current_buffer.get_line_text(0).startswith("red")
    assert (terminal.board.cursor.x, terminal.board.cursor.y) == (4, 1)
    assert terminal.board.title.title == "Board"
