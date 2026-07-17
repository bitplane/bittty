"""XTWINOPS window manipulation: state stored as board registers, plus reports."""

from bittty.caps import DisplayCaps
from bittty.parser import Parser
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _term(width=80, height=24):
    terminal = Board(width=width, height=height)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    return terminal, Parser(terminal.board), transport


def test_iconify_state():
    terminal, parser, _ = _term()
    parser.feed("\x1b[2t")  # iconify
    assert terminal.board.window_iconified is True
    parser.feed("\x1b[1t")  # de-iconify
    assert terminal.board.window_iconified is False


def test_move_and_report_position():
    terminal, parser, transport = _term()
    parser.feed("\x1b[3;120;40t")  # move window to (120, 40)
    assert terminal.board.window_position == (120, 40)
    parser.feed("\x1b[13t")  # report position
    assert transport.data[-1] == "\x1b[3;120;40t"


def test_report_iconify_state():
    terminal, parser, transport = _term()
    parser.feed("\x1b[11t")  # report — not iconified
    assert transport.data[-1] == "\x1b[1t"
    parser.feed("\x1b[2t\x1b[11t")  # iconify then report
    assert transport.data[-1] == "\x1b[2t"


def test_maximize_and_fullscreen():
    terminal, parser, _ = _term()
    parser.feed("\x1b[9;1t")  # maximize
    assert terminal.board.window_maximized is True
    parser.feed("\x1b[10;1t")  # fullscreen on
    assert terminal.board.window_fullscreen is True
    parser.feed("\x1b[10;2t")  # fullscreen toggle -> off
    assert terminal.board.window_fullscreen is False


def test_raise_lower_refresh_are_signals():
    terminal, parser, _ = _term()
    parser.feed("\x1b[5t\x1b[6t\x1b[7t")
    assert terminal.board.window_requests == ["raise", "lower", "refresh"]


def test_report_window_title():
    terminal, parser, transport = _term()
    parser.feed("\x1b]2;hello\x07")  # set title
    parser.feed("\x1b[21t")  # report window title
    assert transport.data[-1] == "\x1b]lhello\x1b\\"


def test_resize_to_lines():
    terminal, parser, _ = _term()
    parser.feed("\x1b[40t")  # Ps >= 24 -> resize to 40 lines
    assert terminal.board.height == 40


def test_pixel_reports_from_display_caps():
    terminal, parser, transport = _term()
    terminal.board.set_display_caps(DisplayCaps(cell_px=(8, 16), window_px=(640, 480)))
    parser.feed("\x1b[14t")  # window size in pixels
    assert transport.data[-1] == "\x1b[4;480;640t"
    parser.feed("\x1b[16t")  # cell size in pixels
    assert transport.data[-1] == "\x1b[6;16;8t"
    parser.feed("\x1b[15t")  # screen size in pixels (uses window_px)
    assert transport.data[-1] == "\x1b[5;480;640t"


def test_pixel_reports_zero_without_caps():
    terminal, parser, transport = _term()
    parser.feed("\x1b[16t")  # no caps pushed -> 0;0
    assert transport.data[-1] == "\x1b[6;0;0t"
