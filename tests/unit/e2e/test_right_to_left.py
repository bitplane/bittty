"""DECRLM (mode 34): the right-to-left cursor direction, from the VT510 reference manual.

Columns keep their numbering; a printed character goes at the cursor and the cursor moves one
column left. In insert mode the characters from the cursor to the left margin shift left. BS
moves right; CR, NEL and LF under LNM go to the right-most column; a character printed at
column 1 is followed, under autowrap, at the right margin of the next line. CUP, CUF and CUB,
and the erasing and editing functions, are unaffected.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import BITTTY, VT510, XTERM

RTL = "\x1b[?34h"


def _run(sequence, model=VT510):
    board = Board(width=12, height=4, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence)
    lines = [board.blitter.current_page.get_line_text(y).rstrip() for y in range(3)]
    return lines, (board.cursor.y + 1, board.cursor.display_x + 1), wire.data


@pytest.mark.parametrize(
    ("sequence", "lines", "cursor"),
    [
        (RTL + "\x1b[1;10Habc", ["       cba", "", ""], (1, 7)),
        (RTL + "\x1b[1;10Hab\rc", ["        ba c", "", ""], (1, 11)),  # CR: the right-most column
        (RTL + "\x1b[1;10Hab\x08\x08c", ["        bc", "", ""], (1, 9)),  # BS moves right
        (RTL + "\x1b[1;3Habcd", ["cba", "           d", ""], (2, 11)),  # autowrap at column 1
        (RTL + "\x1b[?7l\x1b[1;3Habcd", ["dba", "", ""], (1, 1)),  # without it, column 1 is overwritten
        (RTL + "\x1b[1;5Hab\x1bEc", ["   ba", "           c", ""], (2, 11)),  # NEL
        (RTL + "\x1b[20h\x1b[1;5Hab\nc", ["   ba", "           c", ""], (2, 11)),  # LF under LNM
        (RTL + "\x1b[1;5Hab\nc", ["   ba", "  c", ""], (2, 2)),  # a plain LF only moves down
        ("abcdef\x1b[1;4H" + RTL + "\x1b[4hX", ["bcdXef", "", ""], (1, 3)),  # IRM shifts toward the left
        (RTL + "\x1b[1;5Hab\x1b[2Cc\x1b[3Dd", ["d  bc", "", ""], (1, 1)),  # CUF and CUB as ever
        ("abcdef\x1b[1;2H" + RTL + "\x1b[P\x1b[@\x1b[K", ["a", "", ""], (1, 2)),  # editing as ever
        (RTL + "\x1b[1;5Hab\x1b[?34lcd\r", ["  cda", "", ""], (1, 1)),  # reset: left to right again
        (RTL + "\x1b[1;6H中a", ["   a中", "", ""], (1, 3)),  # a wide character takes two columns
        ("\x1b[?69h\x1b[4;9s" + RTL + "\x1b[1;5Habc", ["   ba", "        c", ""], (2, 8)),  # margins
    ],
)
def test_right_to_left(sequence, lines, cursor):
    got_lines, got_cursor, _ = _run(sequence)
    assert (got_lines, got_cursor) == (lines, cursor)


@pytest.mark.parametrize(("model", "status"), [(VT510, 2), (BITTTY, 2), (XTERM, 0)])
def test_decrqm(model, status):
    _, _, replies = _run("\x1b[?34$p", model)
    assert replies == [f"\x1b[?34;{status}$y"]
