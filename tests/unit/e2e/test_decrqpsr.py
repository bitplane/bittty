"""DECRQPSR (CSI Ps $ w): cursor information (DECCIR) and tab stop (DECTABSR) reports.

Replies captured from xterm 407 (80x24).
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.parser import Parser


def _driver():
    board = Board(width=80, height=24)
    transport = MemoryConnection()
    board.host.attach(transport)
    return Parser(board), transport


@pytest.mark.parametrize(
    ("setup", "report"),
    [
        ("", "1;1;1;@;@;@;0;2;@;BBBB"),
        ("\x1b[5;10H\x1b[1;4;5;7m", "5;10;1;O;@;@;0;2;@;BBBB"),  # bold, underline, blink, reverse
        ('\x1b[5;10H\x1b[1"q', "5;10;1;@;A;@;0;2;@;BBBB"),  # DECSCA protected
        ("\x1b[5;20r\x1b[?69h\x1b[10;60s\x1b[?6h\x1b[3;4H", "7;13;1;@;@;A;0;2;@;BBBB"),  # origin: absolute position
        ("\x1b[1;80HX", "1;80;1;@;@;H;0;2;@;BBBB"),  # pending wrap
        ("\x1b[1;80HX\x1b[?7l", "1;80;1;@;@;H;0;2;@;BBBB"),  # which survives DECAWM reset
        ("\x1bN", "1;1;1;@;@;B;0;2;@;BBBB"),  # SS2
        ("\x1bN\x1bO", "1;1;1;@;@;D;0;2;@;BBBB"),  # SS3 replaces SS2
        ("\x1b(0\x0e", "1;1;1;@;@;@;1;2;@;0BBB"),  # G0 graphics, SO
        ("\x1b~", "1;1;1;@;@;@;0;1;@;BBBB"),  # LS1R
        ("\x1bn\x1b}", "1;1;1;@;@;@;2;2;@;BBBB"),  # LS2, LS2R
    ],
)
def test_deccir_reports_cursor_information(setup, report):
    parser, transport = _driver()
    parser.feed(setup)
    parser.feed("\x1b[1$w")
    assert transport.data == [f"\x1bP1$u{report}\x1b\\"]


@pytest.mark.parametrize(
    ("setup", "report"),
    [
        ("", "9/17/25/33/41/49/57/65/73"),
        ("\x1b[3g\x1b[1;5H\x1bH\x1b[1;20H\x1bH\x1b[1;80H\x1bH", "5/20/80"),
        ("\x1b[3g", ""),
    ],
)
def test_dectabsr_reports_tab_stops(setup, report):
    parser, transport = _driver()
    parser.feed(setup)
    parser.feed("\x1b[2$w")
    assert transport.data == [f"\x1bP2$u{report}\x1b\\"]


@pytest.mark.parametrize("ps", ["", "0", "3"])
def test_other_presentation_state_requests_get_no_reply(ps):
    parser, transport = _driver()
    parser.feed(f"\x1b[{ps}$w")
    assert transport.data == []
