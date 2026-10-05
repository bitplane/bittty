"""What interrupts a control sequence or string, captured from xterm 407 (the DEC parser)."""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import XTERM


def _run(sequence):
    board = Board(width=80, height=24, model=XTERM)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence.encode())
    return board, wire


def _lines(board):
    return [board.blitter.current_page.get_line_text(y).rstrip() for y in range(2)]


@pytest.mark.parametrize(
    ("sequence", "lines"),
    [
        ("\x1bP1;0;0!zab\x1b[3CX", ["   X", ""]),  # ESC ends a DCS and begins the next sequence
        ("\x1b]2;ab\x1b[3CX", ["   X", ""]),  # OSC
        ("\x1b_ab\x1b[3CX", ["   X", ""]),  # APC
        ("\x1b^ab\x1b[3CX", ["   X", ""]),  # PM
        ("\x1bXab\x1b[3CX", ["   X", ""]),  # SOS
        ("\x1b]2;ab\x1b\x1b[3CX", ["   X", ""]),
        ("\x1b]2;ab\x1bDX", ["", "X"]),
        ("\x1bP$qm\x1b\x1b\\X", ["X", ""]),
        ("\x1b[1\x1b[3CX", ["   X", ""]),  # ESC ends a CSI too
        ("\x1b[5\x1bDX", ["", "X"]),
        ("\x1b[1\x1b\x1b[3CX", ["   X", ""]),
        ("\x1b[3\nCX", ["", "   X"]),  # a C0 control inside a CSI acts at once; the CSI carries on
        ("a\x1b\\b", ["ab", ""]),  # a stray ST does nothing
    ],
)
def test_interruptions(sequence, lines):
    assert _lines(_run(sequence)[0]) == lines


@pytest.mark.parametrize("string", ["\x1bP$qm", "\x1b]10;?"])
def test_a_string_ended_by_escape_is_abandoned(string):
    """No reply: an ESC that is not ST aborts the string rather than terminating it."""
    board, wire = _run(string + "\x1bD")
    assert wire.data == []


def test_a_title_ended_by_escape_is_not_set():
    board, _ = _run("\x1b]2;ab\x1bD")
    assert board.title.title != "ab"


def test_escape_at_the_end_of_a_chunk_waits_for_the_next():
    board, wire = _run("\x1bP$qm\x1b")
    board.feed_host_data("\\".encode())
    assert wire.data == ["\x1bP1$r0m\x1b\\"]
