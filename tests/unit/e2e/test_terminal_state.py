"""DECRQTSR (CSI 1 $ u) reports the terminal state as DECTSR (DCS 1 $ s D...D ST); DECRSTS
(DCS 1 $ p D...D ST) restores it.

The VT510 manual leaves DECTSR's contents to the terminal ("Software should not expect the
format ... to be the same for all terminals"). bittty's is the hex of the control functions
that re-establish the state, so a restore is a replay. xterm 407 does not answer DECRQTSR.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import BITTTY, LINUX, VT510, XTERM

STATE = (
    "\x1b[?5;6;69h\x1b[4h"  # reverse screen, origin, left/right margins; insert
    "\x1b[?7l"  # no autowrap
    "\x1b[3;20r\x1b[5;60s"  # margins
    "\x1b[2*x"  # DECSACE rectangle
    '\x1b[1"q'  # DECSCA protected
    "\x1b[1;4;38;5;100;48;2;1;2;3m"  # SGR
    "\x1b)0\x1b-A\x0e"  # G1 = DEC Special Graphics then Latin-1, invoked into GL
    "\x1b[3g\x1bH\x1b[4;9H\x1bH"  # tab stops: cleared, then two set
    "\x1b[6;30H"  # cursor
)


def _board(model=VT510):
    board = Board(width=80, height=24, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    return board, wire


def _snapshot(board, wire):
    """Everything the state covers, as the host would read it back."""
    wire.data.clear()
    board.feed_host_data(
        "\x1b[1$w\x1b[2$w"  # DECCIR, DECTABSR
        "\x1bP$qr\x1b\\\x1bP$qs\x1b\\\x1bP$qm\x1b\\\x1bP$q*x\x1b\\"
        "\x1b[?5$p\x1b[?6$p\x1b[?7$p\x1b[?69$p\x1b[4$p"
    )
    return list(wire.data)


@pytest.mark.parametrize("model", [VT510, BITTTY])
def test_a_restored_state_reads_back_the_same(model):
    board, wire = _board(model)
    board.feed_host_data(STATE)
    before = _snapshot(board, wire)
    wire.data.clear()
    board.feed_host_data("\x1b[1$u")
    (report,) = wire.data
    assert report.startswith("\x1bP1$s") and report.endswith("\x1b\\")

    board.feed_host_data("\x1bc")
    assert _snapshot(board, wire) != before
    board.feed_host_data("\x1bP1$p" + report[5:])
    assert _snapshot(board, wire) == before


def test_the_report_is_hex():
    board, wire = _board()
    board.feed_host_data("\x1b[1$u")
    data = wire.data[0][5:-2]
    assert data == data.upper() and bytes.fromhex(data)


def test_restoring_leaves_the_screen_alone():
    board, wire = _board()
    board.feed_host_data("\x1b[1$u")
    report = wire.data[0]
    board.feed_host_data("hello\x1bP1$p" + report[5:])
    assert board.capture_text() == "hello"


@pytest.mark.parametrize("data", ["XYZ", "414", ""])
def test_a_malformed_restore_is_ignored(data):
    board, _ = _board()
    board.feed_host_data("\x1b[5;10r\x1bP1$p" + data + "\x1b\\")
    assert (board.blitter.scroll_top, board.blitter.scroll_bottom) == (4, 9)


@pytest.mark.parametrize("request_", ["\x1b[$u", "\x1b[0$u", "\x1b[3$u"])
def test_other_reports_are_ignored(request_):
    board, wire = _board()
    board.feed_host_data(request_)
    assert wire.data == []


@pytest.mark.parametrize("model", [XTERM, LINUX])
def test_a_terminal_without_state_reports_does_not_answer(model):
    board, wire = _board(model)
    board.feed_host_data("\x1b[1$u")
    assert wire.data == []
