"""A zero count means one, as a missing one does. Captured from xterm 407 (80x24)."""

import pytest

from bittty import Board
from bittty.model import XTERM

DIGITS = "0123456789" * 8


def _run(sequence):
    board = Board(width=80, height=24, model=XTERM)
    board.feed_host_data(f"\x1b[2;1H{DIGITS}\x1b[2;15H{sequence}".encode())
    return board


@pytest.mark.parametrize(
    ("sequence", "row", "column"),
    [
        ("\x1b[0A", 1, 15),  # CUU
        ("\x1b[0B", 3, 15),  # CUD
        ("\x1b[0C", 2, 16),  # CUF
        ("\x1b[0D", 2, 14),  # CUB
        ("\x1b[0E", 3, 1),  # CNL
        ("\x1b[0F", 1, 1),  # CPL
        ("\x1b[0a", 2, 16),  # HPR
        ("\x1b[0e", 3, 15),  # VPR
        ("\x1b[0I", 2, 17),  # CHT
        ("\x1b[0Z", 2, 9),  # CBT
    ],
)
def test_zero_moves_the_cursor_once(sequence, row, column):
    board = _run(sequence)
    assert (board.cursor.y + 1, board.cursor.x + 1) == (row, column)


@pytest.mark.parametrize(
    ("sequence", "line"),
    [
        ("\x1b[0@", DIGITS[:14] + " " + DIGITS[14:79]),  # ICH
        ("\x1b[0P", DIGITS[:14] + DIGITS[15:]),  # DCH
        ("\x1b[0X", DIGITS[:14] + " " + DIGITS[15:]),  # ECH
        ("\x1b[0'}", DIGITS[:14] + " " + DIGITS[14:79]),  # DECIC
        ("\x1b[0'~", DIGITS[:14] + DIGITS[15:]),  # DECDC
        ("\x1b[0 @", DIGITS[1:]),  # SL
        ("\x1b[0 A", " " + DIGITS[:79]),  # SR
        ("A\x1b[0b", DIGITS[:14] + "AA" + DIGITS[16:]),  # REP
    ],
)
def test_zero_edits_once(sequence, line):
    assert _run(sequence).blitter.current_page.get_line_text(1).rstrip() == line.rstrip()


@pytest.mark.parametrize(("sequence", "moved_to"), [("\x1b[0L", 2), ("\x1b[0M", None), ("\x1b[0S", 0)])
def test_zero_scrolls_once(sequence, moved_to):
    """IL, DL and SU; SD 0 does nothing in xterm and is left alone."""
    page = _run(sequence).blitter.current_page
    rows = [page.get_line_text(y).rstrip() for y in range(3)]
    assert [y for y, text in enumerate(rows) if text == DIGITS] == ([] if moved_to is None else [moved_to])
