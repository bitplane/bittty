"""DEC rectangular-area functions: DECFRA/DECERA/DECSERA/DECCRA/DECCARA/DECRARA."""

from bittty import Board
from bittty.parser import Parser
from bittty.style import Color


def _term():
    board = Board(width=10, height=6)
    return board, Parser(board)


def _rows(board):
    buf = board.blitter.current_page
    return [buf.get_line_text(y) for y in range(board.height)]


def test_decfra_fills_a_rectangle():
    board, parser = _term()
    parser.feed("\x1b[88;2;3;4;6$x")  # fill rows 2-4, cols 3-6 with 'X' (chr 88)
    rows = _rows(board)
    assert rows[0] == " " * 10  # outside untouched
    assert rows[1] == "  XXXX    "  # row 2, cols 3-6
    assert rows[3] == "  XXXX    "  # row 4
    assert rows[4] == " " * 10  # row 5 untouched


def test_decera_erases_a_rectangle():
    board, parser = _term()
    parser.feed("\x1b[88;1;1;6;10$x")  # fill everything with X
    parser.feed("\x1b[2;3;4;6$z")  # erase rows 2-4, cols 3-6 (0-based indices 2-5)
    assert _rows(board)[2] == "XX    XXXX"  # middle punched out


def test_deccra_copies_a_rectangle():
    board, parser = _term()
    parser.feed("\x1b[1;1HABCD")  # row 1: "ABCD"
    parser.feed("\x1b[1;1;1;4;1;3;1;1$v")  # copy row1 cols1-4 to row 3 col 1
    assert _rows(board)[2].startswith("ABCD")


def test_deccara_changes_attributes_in_a_rectangle():
    board, parser = _term()
    parser.feed("\x1b[1;1Hhello")
    parser.feed("\x1b[1;1;1;3;31$r")  # make cols 1-3 of row 1 red
    buf = board.blitter.current_page
    assert buf.get_cell(0, 0)[0].fg == Color("indexed", 1)  # 'h' is red
    assert buf.get_cell(3, 0)[0].fg is None  # 'l' (col 4) unchanged


def test_decsera_rectangle_respects_protection():
    board, parser = _term()
    parser.feed('\x1b[1"q')  # protect
    parser.feed("\x1b[1;1HAB")
    parser.feed('\x1b[0"q')  # unprotect
    parser.feed("CD")
    parser.feed("\x1b[1;1;1;10${")  # selective-erase row 1
    assert _rows(board)[0].startswith("AB  ")  # AB protected, CD erased


def test_decfra_ignores_a_character_code_outside_the_printable_ranges():
    """DEC restricts DECFRA's Pch to 32-126 and 160-255; anything else is ignored.

    999999999 used to reach chr() and raise ValueError straight out of the
    parser feed, into whatever application was embedding the board.
    """
    board = Board(width=6, height=3)
    parser = Parser(board)
    parser.feed("\x1b[88;1;1;3;6$x")  # 'X' (88) is in range, so this must land
    assert board.capture_text() == "\n".join(["XXXXXX"] * 3)

    parser.feed("\x1b[999999999;1;1;3;6$x")
    parser.feed("\x1b[127;1;1;3;6$x")  # DEL: outside the printable ranges too
    parser.feed("\x1b[159;1;1;3;6$x")  # the C1 gap between 126 and 160

    assert board.capture_text() == "\n".join(["XXXXXX"] * 3)
