"""Modes a terminal knows but the host cannot change: DECRQM reports them permanently set (3)
or reset (4). xterm's are captured from xterm 407; the DEC terminals' from their user guides'
DECRQM tables (the ANSI modes of ECMA-48 that DEC never implemented, and DECHCCM)."""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import BITTTY, VT320, VT420, VT510, XTERM


def _status(model, mode):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(f"\x1b[{mode}$p\x1b[{mode}h\x1b[{mode}$p")
    return wire.data


XTERM_FIXED = {
    **dict.fromkeys(["?8", "?10", "?11", "?16", "?46", "?53", "?59", "?60", "?61", "?64", "?68", "?73", "?81"], 4),
    "?14": 3,
    **dict.fromkeys(["1", "5", "7", "10", "11", "13", "14", "15", "16", "17", "18", "19"], 4),
}


@pytest.mark.parametrize(("mode", "status"), XTERM_FIXED.items())
def test_xterm_fixed_modes(mode, status):
    assert _status(XTERM, mode) == [f"\x1b[{mode};{status}$y"] * 2  # and setting it changes nothing


@pytest.mark.parametrize("mode", ["?95", "?1052", "?1053"])
def test_modes_xterm_does_not_know(mode):
    assert _status(XTERM, mode) == [f"\x1b[{mode};0$y"] * 2


@pytest.mark.parametrize("mode", ["?95", "?1052", "?1053"])
def test_bittty_keeps_them(mode):
    assert _status(BITTTY, mode)[0] != f"\x1b[{mode};0$y"


@pytest.mark.parametrize("model", [VT420, VT510])
@pytest.mark.parametrize("mode", ["1", "5", "7", "10", "11", "13", "14", "15", "16", "17", "18", "19", "?60"])
def test_vt420_permanently_reset_modes(model, mode):
    assert _status(model, mode) == [f"\x1b[{mode};4$y"] * 2


def test_vt320_horizontal_editing_is_permanently_reset():
    assert _status(VT320, "10") == ["\x1b[10;4$y"] * 2
