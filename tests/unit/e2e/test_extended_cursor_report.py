"""DECXCPR: CSI ? 6 n reports the cursor with its page, CSI ? Pl ; Pc ; Pp R (VT420, xterm 407 captured)."""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import BITTTY, LINUX, VT220, VT510, XTERM


def _run(sequence, model):
    board = Board(width=80, height=24, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence)
    return wire.data


@pytest.mark.parametrize("model", [XTERM, VT510, BITTTY])
def test_extended_cursor_position_report(model):
    assert _run("\x1b[5;7H\x1b[?6n", model) == ["\x1b[?5;7;1R"]


def test_it_carries_the_cursor_page():
    assert _run("\x1b[2U\x1b[5;7H\x1b[?6n", VT510) == ["\x1b[?5;7;3R"]


def test_the_plain_report_has_no_page():
    assert _run("\x1b[5;7H\x1b[6n", XTERM) == ["\x1b[5;7R"]


@pytest.mark.parametrize("model", [VT220, LINUX])
def test_terminals_before_the_vt420_do_not_answer(model):
    assert _run("\x1b[?6n", model) == []
