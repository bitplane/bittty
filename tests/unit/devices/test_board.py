from bittty import Parser, Terminal, TerminalBoard, TerminalOperationSink
from bittty.operations import Operation
from bittty.style import parse_sgr_sequence


def test_terminal_builds_board_and_exposes_device_slots():
    terminal = Terminal(width=12, height=4)

    assert isinstance(terminal.board, TerminalBoard)
    assert terminal.parser.sink is terminal.board
    assert terminal.board.devices["cursor"] is terminal.cursor
    assert terminal.board.devices["host"] is terminal.host
    assert terminal.board.devices["screen"] is terminal.screen
    assert terminal.board.devices["style"] is terminal.style
    assert terminal.board.devices["title"] is terminal.title_device
    assert terminal.board.get_device("keyboard") is terminal.keyboard
    assert terminal.board.get_device("mouse") is terminal.mouse


def test_parser_reuses_existing_terminal_board_by_default():
    terminal = Terminal(width=12, height=4)

    parser = Parser(terminal)

    assert parser.sink is terminal.board
    assert terminal.cursor is terminal.board.cursor


def test_terminal_operation_sink_wraps_existing_board():
    terminal = Terminal(width=12, height=4)

    sink = TerminalOperationSink(terminal)
    sink.handle_operation(Operation("text", "PRINT", ("ok",), "ok"))

    assert sink.board is terminal.board
    assert terminal.current_buffer.get_line_text(0).startswith("ok")


def test_board_routes_operations_to_plugged_in_devices():
    terminal = Terminal(width=12, height=4)
    board = terminal.board

    board.handle_operation(Operation("style", "SGR", (parse_sgr_sequence("\x1b[31m"), False), "\x1b[31m"))
    board.handle_operation(Operation("text", "PRINT", ("red",), "red"))
    board.handle_operation(Operation("cursor", "CUP", (4, 1), "\x1b[2;5H"))
    board.handle_operation(Operation("title", "SET_WINDOW_TITLE", ("Board",), "\x1b]2;Board\x07"))

    assert terminal.current_buffer.get_line_text(0).startswith("red")
    assert (terminal.cursor_x, terminal.cursor_y) == (4, 1)
    assert terminal.title == "Board"
