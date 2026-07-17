"""Newly supported CSI final bytes: CNL/CPL, HPA/HPR/VPR, CHT/CBT, TBC, DECSCUSR."""

from bittty.parser import Parser
from bittty import Board


def _term():
    terminal = Board(width=40, height=10)
    return terminal, Parser(terminal.board)


def test_cnl_and_cpl_move_to_column_zero():
    terminal, parser = _term()
    parser.feed("\x1b[5;10H\x1b[2E")  # CNL 2: down 2 lines, column 0
    assert (terminal.board.cursor.x, terminal.board.cursor.y) == (0, 6)
    parser.feed("\x1b[3;10H\x1b[1F")  # CPL 1: up 1 line, column 0
    assert (terminal.board.cursor.x, terminal.board.cursor.y) == (0, 1)


def test_hpa_hpr_and_vpr():
    terminal, parser = _term()
    parser.feed("\x1b[10`")  # HPA -> column 10 (0-based 9)
    assert terminal.board.cursor.x == 9
    parser.feed("\x1b[3a")  # HPR +3
    assert terminal.board.cursor.x == 12
    parser.feed("\x1b[1;1H\x1b[4e")  # VPR +4
    assert terminal.board.cursor.y == 4


def test_forward_backward_tab_and_tab_clear():
    terminal, parser = _term()  # default tab stops at 8, 16, 24, 32
    parser.feed("\x1b[1;1H\x1b[2I")  # CHT 2 -> second tab stop
    assert terminal.board.cursor.x == 16
    parser.feed("\x1b[1Z")  # CBT 1 -> previous tab stop
    assert terminal.board.cursor.x == 8
    parser.feed("\x1b[3g")  # TBC 3 -> clear every tab stop
    assert terminal.board.cursor.tab_stops == set()


def test_decscusr_sets_cursor_shape_and_blink():
    terminal, parser = _term()
    parser.feed("\x1b[4 q")  # steady underline
    assert terminal.board.cursor.shape == "underline"
    assert terminal.board.modes.cursor_blinking is False
    parser.feed("\x1b[5 q")  # blinking bar
    assert terminal.board.cursor.shape == "bar"
    assert terminal.board.modes.cursor_blinking is True
