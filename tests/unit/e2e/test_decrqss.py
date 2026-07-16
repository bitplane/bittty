"""DECRQSS (DCS $q ... ST): reporting the current setting back to the host."""

from bittty.parser import Parser
from bittty.terminal import Terminal


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _driver():
    terminal = Terminal(width=80, height=24)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    return Parser(terminal.board), transport


def test_decrqss_reports_current_sgr():
    parser, transport = _driver()
    parser.feed("\x1b[1;31m")  # bold, red
    parser.feed("\x1bP$qm\x1b\\")  # DECRQSS for SGR
    assert transport.data == ["\x1bP1$r1;31m\x1b\\"]


def test_decrqss_reports_default_sgr_as_zero():
    parser, transport = _driver()
    parser.feed("\x1bP$qm\x1b\\")
    assert transport.data == ["\x1bP1$r0m\x1b\\"]


def test_decrqss_reports_scroll_region():
    parser, transport = _driver()
    parser.feed("\x1b[3;20r")  # DECSTBM
    parser.feed("\x1bP$qr\x1b\\")
    assert transport.data == ["\x1bP1$r3;20r\x1b\\"]


def test_decrqss_reports_cursor_style():
    parser, transport = _driver()
    parser.feed("\x1b[4 q")  # steady underline
    parser.feed("\x1bP$q q\x1b\\")
    assert transport.data == ["\x1bP1$r4 q\x1b\\"]


def test_decrqss_unsupported_request_reports_invalid():
    parser, transport = _driver()
    parser.feed("\x1bP$qZ\x1b\\")  # not a setting we can report
    assert transport.data == ["\x1bP0$rZ\x1b\\"]
