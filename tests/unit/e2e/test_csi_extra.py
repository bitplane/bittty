"""Newly supported CSI final bytes: CNL/CPL, HPA/HPR/VPR, CHT/CBT, TBC, DECSCUSR."""

import pytest

from bittty import Board
from bittty.parser import Parser


def _term():
    board = Board(width=40, height=10)
    return board, Parser(board)


def test_cnl_and_cpl_move_to_column_zero():
    board, parser = _term()
    parser.feed("\x1b[5;10H\x1b[2E")  # CNL 2: down 2 lines, column 0
    assert (board.cursor.x, board.cursor.y) == (0, 6)
    parser.feed("\x1b[3;10H\x1b[1F")  # CPL 1: up 1 line, column 0
    assert (board.cursor.x, board.cursor.y) == (0, 1)


def test_hpa_hpr_and_vpr():
    board, parser = _term()
    parser.feed("\x1b[10`")  # HPA -> column 10 (0-based 9)
    assert board.cursor.x == 9
    parser.feed("\x1b[3a")  # HPR +3
    assert board.cursor.x == 12
    parser.feed("\x1b[1;1H\x1b[4e")  # VPR +4
    assert board.cursor.y == 4


def test_forward_backward_tab_and_tab_clear():
    board, parser = _term()  # default tab stops at 8, 16, 24, 32
    parser.feed("\x1b[1;1H\x1b[2I")  # CHT 2 -> second tab stop
    assert board.cursor.x == 16
    parser.feed("\x1b[1Z")  # CBT 1 -> previous tab stop
    assert board.cursor.x == 8
    parser.feed("\x1b[3g")  # TBC 3 -> clear every tab stop
    assert board.cursor.tab_stops == set()


def test_decscusr_sets_cursor_shape_and_blink():
    board, parser = _term()
    parser.feed("\x1b[4 q")  # steady underline
    assert board.cursor.shape == "underline"
    assert board.modes.cursor_blinking is False
    parser.feed("\x1b[5 q")  # blinking bar
    assert board.cursor.shape == "bar"
    assert board.modes.cursor_blinking is True


@pytest.mark.parametrize("count", (1000, 1001, 1234, 9999))
@pytest.mark.parametrize("size", ((10, 3), (7, 4), (3, 2)))
def test_hostile_repeat_count_is_clamped_without_changing_the_screen(size, count):
    """REP takes its count off the wire, so it must not allocate unbounded.

    The clamp has to stay congruent to the count modulo the width or the final
    partial row lands in the wrong place, so this compares against the real
    thing rather than asserting a hand-computed screen.
    """
    width, height = size
    clamped = Board(width=width, height=height)
    clamped.parser.feed("A")
    clamped.parser.feed(f"\x1b[{count}b")

    literal = Board(width=width, height=height)
    literal.parser.feed("A")
    literal.parser.feed("A" * count)

    assert clamped.capture_text() == literal.capture_text()


def test_absurd_repeat_count_does_not_allocate_a_string_for_it():
    """CSI 999999999 b once built a 45GB string and hung the emulator."""
    board = Board(width=80, height=24)
    board.parser.feed("A")
    board.parser.feed("\x1b[999999999b")

    assert board.capture_text() == "\n".join(["A" * 80] * 24)


def test_non_numeric_csi_parameter_reads_as_absent():
    """ECMA-48 parameters are digits; anything else takes the default.

    A leading sub-parameter colon used to store the raw string in the parameter
    tuple, which every handler downstream then did arithmetic on.
    """
    board = Board(width=10, height=3)
    board.parser.feed("line1\r\nline2\r\nline3")

    board.parser.feed("\x1b[:H")  # CUP with an unparseable row: home, not a crash
    board.parser.feed("X")

    assert board.capture_text().splitlines()[0] == "Xine1"
