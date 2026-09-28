"""Cursor edge cases, captured from xterm 407 (80x24) through DECCIR and print-screen."""

import pytest

from bittty import Board
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
