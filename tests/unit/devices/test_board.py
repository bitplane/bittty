from bittty import Board, Parser
from bittty.operations import Operation
from bittty.style import parse_sgr_sequence


def test_terminal_builds_board_and_exposes_device_slots():
    terminal = Board(width=12, height=4)

    assert isinstance(terminal, Board)
    assert terminal.parser.sink is terminal
    assert terminal.devices["cursor"] is terminal.cursor
    assert terminal.devices["host"] is terminal.host
    assert terminal.devices["blitter"] is terminal.blitter
    assert terminal.devices["style"] is terminal.style
    assert terminal.devices["title"] is terminal.title
    assert terminal.get_device("keyboard") is terminal.keyboard
    assert terminal.get_device("mouse") is terminal.mouse


def test_parser_reuses_existing_terminal_board_by_default():
    terminal = Board(width=12, height=4)

    parser = Parser(terminal)

    assert parser.sink is terminal
    assert terminal.cursor is terminal.cursor


def test_board_routes_operations_to_plugged_in_devices():
    terminal = Board(width=12, height=4)
    board = terminal

    board.handle_operation(Operation("SGR", (parse_sgr_sequence("\x1b[31m"), False), "\x1b[31m"))
    board.handle_operation(Operation("PRINT", ("red",), "red"))
    board.handle_operation(Operation("CUP", (4, 1), "\x1b[2;5H"))
    board.handle_operation(Operation("SET_WINDOW_TITLE", ("Board",), "\x1b]2;Board\x07"))

    assert terminal.blitter.current_buffer.get_line_text(0).startswith("red")
    assert (terminal.cursor.x, terminal.cursor.y) == (4, 1)
    assert terminal.title.title == "Board"
