from unittest.mock import Mock

from bittty import constants
from bittty.operations import Operation
from bittty.terminal import Terminal


def test_control_device_routes_c0_controls_to_devices():
    terminal = Terminal(width=12, height=4)
    control = terminal.parser.sink.control

    terminal.cursor.set_position(5, 1)
    control.handle_operation(Operation("control", "C0_BS", raw=constants.BS))
    assert terminal.cursor.x == 4

    control.handle_operation(Operation("control", "C0_HT", raw=constants.HT))
    assert terminal.cursor.x == 8

    control.handle_operation(Operation("control", "C0_CR", raw=constants.CR))
    assert terminal.cursor.x == 0

    control.handle_operation(Operation("control", "C0_LF", raw=constants.LF))
    assert terminal.cursor.y == 2


def test_control_device_shift_and_tab_stop_controls():
    terminal = Terminal(width=12, height=4)
    control = terminal.parser.sink.control

    control.handle_operation(Operation("control", "C0_SO", raw=constants.SO))
    assert terminal.charset.current_charset == 1

    control.handle_operation(Operation("control", "C0_SI", raw=constants.SI))
    assert terminal.charset.current_charset == 0

    terminal.cursor.set_position(3, 0)
    control.handle_operation(Operation("control", "HTS", raw="\x1bH"))
    terminal.cursor.set_position(0, 0)
    control.handle_operation(Operation("control", "C0_HT", raw=constants.HT))
    assert terminal.cursor.x == 3


def test_query_device_reports_cursor_and_device_status():
    terminal = Terminal(width=80, height=24)
    query = terminal.parser.sink.query
    terminal.respond = Mock()

    terminal.cursor.set_position(10, 5)
    query.handle_operation(Operation("query", "CPR", (6,), "\x1b[6n"))
    query.handle_operation(Operation("query", "DSR", (5,), "\x1b[5n"))
    query.handle_operation(Operation("query", "DA1", (0,), "\x1b[c"))

    assert terminal.respond.call_args_list[0].args == ("\x1b[6;11R",)
    assert terminal.respond.call_args_list[1].args == ("\x1b[0n",)
    assert terminal.respond.call_args_list[2].args == ("\x1b[?62;1;6;8;9;15;18;21;22;23c",)


def test_query_device_reports_mode_status_from_mode_device():
    terminal = Terminal(width=80, height=24)
    query = terminal.parser.sink.query
    terminal.respond = Mock()

    terminal.modes.cursor_application_mode = True
    terminal.modes.insert_mode = False

    query.handle_operation(Operation("query", "DECRQM", (1, True), "\x1b[?1$p"))
    query.handle_operation(Operation("query", "DECRQM", (4, False), "\x1b[4$p"))
    query.handle_operation(Operation("query", "DECRQM", (9999, True), "\x1b[?9999$p"))

    assert [call.args[0] for call in terminal.respond.call_args_list] == [
        "\x1b[?1;1$y",
        "\x1b[4;2$y",
        "\x1b[?9999;0$y",
    ]


def test_query_device_reports_osc_colors():
    terminal = Terminal(width=80, height=24)
    query = terminal.parser.sink.query
    terminal.respond = Mock()

    query.handle_operation(Operation("query", "OSC_FOREGROUND_COLOR", raw="\x1b]10;?\x07"))
    query.handle_operation(Operation("query", "OSC_BACKGROUND_COLOR", raw="\x1b]11;?\x07"))

    assert [call.args[0] for call in terminal.respond.call_args_list] == [
        "\x1b]10;rgb:ffff/ffff/ffff\x07",
        "\x1b]11;rgb:0000/0000/0000\x07",
    ]
