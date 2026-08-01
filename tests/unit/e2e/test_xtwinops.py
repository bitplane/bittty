"""XTWINOPS window manipulation: state stored as board registers, plus reports."""

from bittty import constants
from bittty.caps import TerminalCaps
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
    board = Board(width=width, height=height)
    transport = RecordingTransport()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_iconify_state():
    board, parser, _ = _term()
    parser.feed("\x1b[2t")  # iconify
    assert board.window_iconified is True
    parser.feed("\x1b[1t")  # de-iconify
    assert board.window_iconified is False


def test_move_and_report_position():
    board, parser, transport = _term()
    parser.feed("\x1b[3;120;40t")  # move window to (120, 40)
    assert board.window_position == (120, 40)
    parser.feed("\x1b[13t")  # report position
    assert transport.data[-1] == "\x1b[3;120;40t"


def test_report_iconify_state():
    board, parser, transport = _term()
    parser.feed("\x1b[11t")  # report — not iconified
    assert transport.data[-1] == "\x1b[1t"
    parser.feed("\x1b[2t\x1b[11t")  # iconify then report
    assert transport.data[-1] == "\x1b[2t"


def test_maximize_and_fullscreen():
    board, parser, _ = _term()
    parser.feed("\x1b[9;1t")  # maximize
    assert board.window_maximized is True
    parser.feed("\x1b[10;1t")  # fullscreen on
    assert board.window_fullscreen is True
    parser.feed("\x1b[10;2t")  # fullscreen toggle -> off
    assert board.window_fullscreen is False


def test_raise_lower_refresh_are_signals():
    board, parser, _ = _term()
    parser.feed("\x1b[5t\x1b[6t\x1b[7t")
    assert board.window_requests == ["raise", "lower", "refresh"]


def test_report_window_title():
    board, parser, transport = _term()
    parser.feed("\x1b]2;hello\x07")  # set title
    parser.feed("\x1b[21t")  # report window title
    assert transport.data[-1] == "\x1b]lhello\x1b\\"


def test_resize_to_lines():
    board, parser, _ = _term()
    parser.feed("\x1b[40t")  # Ps >= 24 -> resize to 40 lines
    assert board.height == 40


def test_pixel_reports_from_terminal_caps():
    board, parser, transport = _term()
    board.set_caps(TerminalCaps(cell_px=(8, 16), window_px=(640, 480)))
    parser.feed("\x1b[14t")  # window size in pixels
    assert transport.data[-1] == "\x1b[4;480;640t"
    parser.feed("\x1b[16t")  # cell size in pixels
    assert transport.data[-1] == "\x1b[6;16;8t"
    parser.feed("\x1b[15t")  # screen size in pixels (uses window_px)
    assert transport.data[-1] == "\x1b[5;480;640t"


def test_pixel_reports_zero_without_caps():
    board, parser, transport = _term()
    parser.feed("\x1b[16t")  # no caps pushed -> 0;0
    assert transport.data[-1] == "\x1b[6;0;0t"


def test_host_requested_resize_is_bounded():
    """XTWINOPS 8 and DECSLPP take dimensions off the wire.

    `CSI 8;99999;99999 t` asked for a ten-billion-cell grid and took the
    embedding process with it. The chrome's own resizes stay unbounded — those
    are physical facts, not requests from the child.
    """
    board = Board(width=80, height=24)

    board.parser.feed("\x1b[8;99999;99999t")
    assert (board.width, board.height) == (constants.MAX_HOST_COLUMNS, constants.MAX_HOST_ROWS)

    board.parser.feed("\x1b[999999999t")  # DECSLPP
    assert board.height == constants.MAX_HOST_ROWS

    # A chrome-reported resize is a physical fact and is not clamped.
    board.resize(2000, 1500)
    assert (board.width, board.height) == (2000, 1500)
