"""Newly supported CSI final bytes: CNL/CPL, HPA/HPR/VPR, CHT/CBT, TBC, DECSCUSR."""

from bittty.parser import Parser
from bittty import Board


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
