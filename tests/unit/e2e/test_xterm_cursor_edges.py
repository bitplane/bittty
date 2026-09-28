"""Cursor edge cases, captured from xterm 407 (80x24) through DECCIR and print-screen."""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import XTERM

DIGITS = "0123456789" * 8


def _run(sequence):
    board = Board(width=80, height=24, model=XTERM)
    board.feed_host_data(sequence)
    return board


def _cursor(board):
    return board.cursor.y + 1, board.cursor.display_x + 1


def _lines(board, rows=3):
    return [board.blitter.current_page.get_line_text(y).rstrip() for y in range(rows)]


# --- IL/DL return to the left margin --- #


@pytest.mark.parametrize(
    ("sequence", "cursor"),
    [
        ("\x1b[2;15H\x1b[L", (2, 1)),
        ("\x1b[2;15H\x1b[M", (2, 1)),
        ("\x1b[1;10r\x1b[2;15H\x1b[L", (2, 1)),
        ("\x1b[?69h\x1b[10;30s\x1b[2;15H\x1b[L", (2, 10)),  # to the left margin
        ("\x1b[?69h\x1b[10;30s\x1b[2;5H\x1b[L", (2, 5)),  # outside the margins: nothing happens
        ("\x1b[5;10r\x1b[2;15H\x1b[L", (2, 15)),  # outside the scroll region: nothing happens
        ("\x1b[1;75Habcdef\x1b[L", (1, 1)),  # from a pending wrap
    ],
)
def test_il_and_dl_return_to_the_left_margin(sequence, cursor):
    assert _cursor(_run(sequence)) == cursor


# --- pending wrap: what keeps it --- #

FILL = "\x1b[1;75Habcdef"  # f lands in column 80 and the wrap is pending
MARGINS = "\x1b[?69h\x1b[10;30s\x1b[1;25Habcdef"  # f lands on the right margin, column 30


@pytest.mark.parametrize(
    ("sequence", "lines"),
    [
        (FILL + "\tY", [" " * 74 + "abcdef", "Y"]),  # HT has nowhere to go
        (FILL + "\x1b[IY", [" " * 74 + "abcdef", "Y"]),  # CHT
        (MARGINS + "\tY", [" " * 24 + "abcdef", " " * 9 + "Y"]),  # stopped by the right margin
        (FILL + "\x1b['}Y", [" " * 74 + "abcde", "Y"]),  # DECIC
        (FILL + "\x1b['~Y", [" " * 74 + "abcde", "Y"]),  # DECDC
        (FILL + "\x1b9Y", [" " * 74 + "abcdef", "Y"]),  # DECFI at the page border is ignored (DEC; xterm pans)
        (MARGINS + "\x1b9Y", [" " * 23 + "abcdef", " " * 9 + "Y"]),  # at the right margin it pans
        (FILL + "\x1b[?7lY\x1b[?7hZ", [" " * 74 + "abcdeY", "Z"]),  # armed while DECAWM was off
    ],
)
def test_pending_wrap_survives(sequence, lines):
    assert _lines(_run(sequence), 2) == lines


@pytest.mark.parametrize(
    "sequence", [FILL + "\t", FILL + "\x1b['}", FILL + "\x1b9", MARGINS + "\x1b9", FILL + "\x1b[?7lY", MARGINS + "\t"]
)
def test_pending_wrap_is_still_reported(sequence):
    assert _run(sequence).cursor.wrap_pending


# --- DECSC/DECRC save the whole cursor state, per screen --- #

SET = '\x1b[5;10r\x1b[?6h\x1b[3;4H\x1b)0\x0e\x1b[1"q\x1b[1;31m'
UNSET = '\x1b[?6l\x1b)B\x0f\x1b[0"q\x1b[0m\x1b[20;20H'


def _deccir(board):
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data("\x1b[1$w")
    return wire.text[len("\x1bP1$u") : -2]


@pytest.mark.parametrize(
    ("sequence", "report"),
    [
        (SET + "\x1b7" + UNSET + "\x1b8", "7;4;1;A;A;A;1;2;@;B0BB"),  # DECSC
        (SET + "\x1b[s" + UNSET + "\x1b[u", "7;4;1;A;A;A;1;2;@;B0BB"),  # SCOSC
        ("\x1b[?6h\x1b[5;10r\x1b(0\x1b[10;10H\x1b8", "1;1;1;@;@;@;0;2;@;BBBB"),  # nothing saved: defaults
        ("\x1b[20;20H\x1b7\x1b[5;10r\x1b[?6h\x1b8", "20;20;1;@;@;@;0;2;@;BBBB"),  # origin mode restored too
        ("\x1b[5;5H\x1b7\x1b[?1047h\x1b[9;9H\x1b7\x1b[?1047l\x1b8", "5;5;1;@;@;@;0;2;@;BBBB"),  # one slot per screen
        (FILL + "\x1b7\x1b[5;5HQ\x1b8", "1;80;1;@;@;H;0;2;@;BBBB"),  # the pending wrap
    ],
)
def test_decrc_restores_what_decsc_saved(sequence, report):
    board = _run(sequence)
    assert _deccir(board) == report


def test_decrc_restores_a_pending_wrap():
    board = _run(FILL + "\x1b7\x1b[5;5H\x1b8Y")
    assert _lines(board, 2) == [" " * 74 + "abcdef", "Y"]


# --- DECSTR leaves the cursor where it is --- #


@pytest.mark.parametrize(
    ("sequence", "report"),
    [
        ("\x1b[5;5H\x1b[!p", "5;5;1;@;@;@;0;2;@;BBBB"),
        (
            '\x1b[5;10r\x1b[?6h\x1b[1;31m\x1b(0\x1b[1"q\x1b[3;3H\x1b[!p',
            "7;3;1;@;@;@;0;2;@;BBBB",
        ),  # and resets the charsets
        (FILL + "\x1b[!p", "1;80;1;@;@;H;0;2;@;BBBB"),  # with its pending wrap
    ],
)
def test_decstr_keeps_the_cursor(sequence, report):
    assert _deccir(_run(sequence)) == report
