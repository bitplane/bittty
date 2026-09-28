"""CRT settings the chrome carries out, kept on the board for it to read.

DECCRTSM (97, VT510): the CRT saver blanks the screen after 30 minutes without activity, and
is enabled by default; it drives the same blank-timeout register as linux's setterm. DECOSCNM
(106, VT510): overscan, disabled by default. DECINLM (9, VT100): interlace, 480 scan lines
rather than 240, with "no increase in character resolution".
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import LINUX, VT100, VT510, XTERM


def _run(sequence, model):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence)
    return board, wire.data


@pytest.mark.parametrize(
    ("sequence", "timeout", "status"),
    [("", 30, 1), ("\x1b[?97l", 0, 2), ("\x1b[?97l\x1b[?97h", 30, 1), ("\x1b[?97l\x1bc", 0, 2)],  # a Set-Up setting
)
def test_crt_saver(sequence, timeout, status):
    board, replies = _run(sequence + "\x1b[?97$p", VT510)
    assert board.blank_timeout == timeout and replies == [f"\x1b[?97;{status}$y"]


def test_the_linux_blank_timeout_is_the_same_register():
    board, _ = _run("\x1b[9;10]", LINUX)
    assert board.blank_timeout == 10


@pytest.mark.parametrize(("model", "mode", "attr"), [(VT510, 106, "overscan"), (VT100, 9, "interlace")])
def test_display_modes(model, mode, attr):
    board, replies = _run(f"\x1b[?{mode}$p\x1b[?{mode}h\x1b[?{mode}$p", model)
    assert replies == [f"\x1b[?{mode};2$y", f"\x1b[?{mode};1$y"] and getattr(board.modes, attr)


def test_xterm_nine_is_still_its_mouse():
    board, _ = _run("\x1b[?9h", XTERM)
    assert not board.modes.interlace and board.modes.mouse_protocol.name == "X10"
