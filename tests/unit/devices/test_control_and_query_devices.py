from bittty import constants
from bittty.operations import Operation
from bittty.terminal import Terminal


class RecordingTransport:
    def __init__(self):
        self.data = []
        self.flush_count = 0

    def write(self, data):
        self.data.append(data)

    def flush(self):
        self.flush_count += 1


def test_control_device_routes_c0_controls_to_devices():
    terminal = Terminal(width=12, height=4)
    control = terminal.parser.sink.control

    terminal.board.cursor.set_position(5, 1)
    control.handle_operation(Operation("C0_BS", raw=constants.BS))
    assert terminal.board.cursor.x == 4

    control.handle_operation(Operation("C0_HT", raw=constants.HT))
    assert terminal.board.cursor.x == 8

    control.handle_operation(Operation("C0_CR", raw=constants.CR))
    assert terminal.board.cursor.x == 0

    control.handle_operation(Operation("C0_LF", raw=constants.LF))
    assert terminal.board.cursor.y == 2


def test_control_device_shift_and_tab_stop_controls():
    terminal = Terminal(width=12, height=4)
    control = terminal.parser.sink.control

    control.handle_operation(Operation("C0_SO", raw=constants.SO))
    assert terminal.board.charset.current_charset == 1

    control.handle_operation(Operation("C0_SI", raw=constants.SI))
    assert terminal.board.charset.current_charset == 0

    terminal.board.cursor.set_position(3, 0)
    control.handle_operation(Operation("HTS", raw="\x1bH"))
    terminal.board.cursor.set_position(0, 0)
    control.handle_operation(Operation("C0_HT", raw=constants.HT))
    assert terminal.board.cursor.x == 3


def test_query_device_reports_cursor_and_device_status():
    terminal = Terminal(width=80, height=24)
    query = terminal.parser.sink.query
    transport = RecordingTransport()
    terminal.board.host.attach(transport)

    terminal.board.cursor.set_position(10, 5)
    query.handle_operation(Operation("CPR", (6,), "\x1b[6n"))
    query.handle_operation(Operation("DSR", (5,), "\x1b[5n"))
    query.handle_operation(Operation("DA1", (0,), "\x1b[c"))

    assert transport.data == [
        "\x1b[6;11R",
        "\x1b[0n",
        "\x1b[?62;1;6;8;9;15;18;21;22;23c",
    ]
    assert transport.flush_count == 3


def test_query_device_reports_mode_status_from_mode_device():
    terminal = Terminal(width=80, height=24)
    query = terminal.parser.sink.query
    transport = RecordingTransport()
    terminal.board.host.attach(transport)

    terminal.board.modes.cursor_application_mode = True
    terminal.board.modes.insert_mode = False

    query.handle_operation(Operation("DECRQM", (1, True), "\x1b[?1$p"))
    query.handle_operation(Operation("DECRQM", (4, False), "\x1b[4$p"))
    query.handle_operation(Operation("DECRQM", (9999, True), "\x1b[?9999$p"))

    assert transport.data == [
        "\x1b[?1;1$y",
        "\x1b[4;2$y",
        "\x1b[?9999;0$y",
    ]
    assert transport.flush_count == 3


def test_palette_device_reports_osc_colors():
    terminal = Terminal(width=80, height=24)
    palette = terminal.board.palette
    transport = RecordingTransport()
    terminal.board.host.attach(transport)

    palette.handle_operation(Operation("OSC_FOREGROUND", ("?",), "\x1b]10;?\x07"))
    palette.handle_operation(Operation("OSC_BACKGROUND", ("?",), "\x1b]11;?\x07"))

    assert transport.data == [
        "\x1b]10;rgb:ffff/ffff/ffff\x07",
        "\x1b]11;rgb:0000/0000/0000\x07",
    ]
    assert transport.flush_count == 2
