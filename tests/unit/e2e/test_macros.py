"""Macros: DECDMAC (DCS Pid;Pdt;Pen ! z D...D ST), DECINVM (CSI Pid * z), DECMSR and DECCKSR.

Behaviour from the VT510 reference manual. xterm 407 reports no macro space and a
zero checksum and stores nothing; its replies are the xterm fixtures here.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import BITTTY, LINUX, VT510, XTERM


def D(body, pid=1, pdt=0, pen=0):
    return f"\x1bP{pid};{pdt};{pen}!z{body}\x1b\\"


def I(pid=1):  # noqa: E743 - DECINVM
    return f"\x1b[{pid}*z"


def _run(sequence, model=VT510):
    board = Board(width=40, height=5, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence)
    return board, wire


def _text(board):
    return board.blitter.current_page.get_line_text(0).rstrip()


@pytest.mark.parametrize("model", [VT510, BITTTY])
@pytest.mark.parametrize(
    ("sequence", "text"),
    [
        (D("hello") + I(), "hello"),
        (D("ab") + I() + I(), "abab"),
        (D("414243", pen=1) + I(), "ABC"),
        (D("!3;41;42", pen=1) + I(), "AAAB"),  # a repeat sequence
        (D("!;41;", pen=1) + I(), "A"),  # which repeats once by default
        (D("1b5b334358", pen=1) + I(), "   X"),  # control functions, hex-encoded
        (D("a\rb") + I(), "ab"),  # controls cannot be sent as text
        (D("a") + D("") + I(), ""),  # redefining deletes the old macro
        (D("a", pid=2) + D("b", pdt=1) + I(2) + I(), "b"),  # Pdt 1 deletes them all first
        (I(5) + "X", "X"),  # undefined: ignored
        (D("q", pid=63) + I(63), "q"),
        (D("q", pid=64) + I(64), ""),  # out of range: ignored
        ("\x1bP;;!zdef\x1b\\" + I(0), "def"),  # defaults: macro 0, as text
        (D("72" + I().encode().hex(), pen=1) + I(), "r"),  # a macro cannot invoke itself
        (D("x", pid=2) + D("79" + I(2).encode().hex(), pen=1) + I(), "yx"),  # but can invoke another
        (D("414", pen=1) + I(), ""),  # malformed hex: ignored
        (D("4G41", pen=1) + I(), ""),
        (D("a", pdt=2) + I(), ""),  # unknown Pdt or Pen: ignored
        (D("a", pen=2) + I(), ""),
        (D("a") + "\x1bc" + I(), ""),  # RIS clears macros
        (D("a") + "\x1b[!p" + I(), "a"),  # DECSTR does not
    ],
)
def test_macros(model, sequence, text):
    assert _text(_run(sequence, model)[0]) == text


def test_what_a_macro_does_stays_done():
    board, _ = _run(D("1b5b316d", pen=1) + I() + "X")
    assert board.blitter.current_page.get_cell(0, 0)[0].bold is True


@pytest.mark.parametrize(
    ("sequence", "reply"),
    [
        ("\x1b[?62n", "\x1b[0384*{"),  # 6 Kbytes, in 16-byte units
        (D("hello") + "\x1b[?62n", "\x1b[0383*{"),
        (D("a" * 7000) + "\x1b[?62n", "\x1b[0384*{"),  # too big: not stored
        (D("!65535;41;", pen=1) + "\x1b[?62n", "\x1b[0384*{"),  # nor its expansion
        ("\x1b[?63n", "\x1bP0!~0000\x1b\\"),
        (D("hello") + "\x1b[?63;7n", "\x1bP7!~FDEC\x1b\\"),  # 16-bit negated sum of the stored bytes
    ],
)
def test_macro_reports(sequence, reply):
    _, wire = _run(sequence)
    assert wire.data == [reply]


@pytest.mark.parametrize(
    ("sequence", "reply"),
    [
        ("\x1b[?62n", "\x1b[0000*{"),
        ("\x1b[?63;1n", "\x1bP1!~0000\x1b\\"),
        ("\x1b[?63;65535n", "\x1bP65535!~0000\x1b\\"),
        (D("hello") + "\x1b[?62n", "\x1b[0000*{"),
    ],
)
def test_xterm_has_no_macro_space(sequence, reply):
    """Captured from xterm 407."""
    board, wire = _run(sequence + I(), XTERM)
    assert wire.data == [reply]
    assert _text(board) == ""


def test_a_terminal_without_macros_does_not_report():
    _, wire = _run("\x1b[?62n\x1b[?63n", LINUX)
    assert wire.data == []
