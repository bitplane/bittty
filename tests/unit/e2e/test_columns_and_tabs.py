"""DECIC/DECDC column edits, HPB/VPB position-backward, and CTC/DECST8C tab control."""

from bittty import Board, MemoryConnection
from bittty.parser import Parser


def _term(width=10, height=6):
    board = Board(width=width, height=height)
    return board, Parser(board)


def _line(board, y=0):
    return board.blitter.current_buffer.get_line_text(y).rstrip()


def test_decic_inserts_columns_at_cursor():
    board, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[3G")  # cursor to column 3 (index 2)
    parser.feed("\x1b[2'}")  # DECIC 2 — insert two blank columns
    assert _line(board) == "AB  CDE"


def test_decdc_deletes_columns_at_cursor():
    board, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[2G")  # cursor to column 2 (index 1)
    parser.feed("\x1b[2'~")  # DECDC 2 — delete two columns
    assert _line(board) == "ADE"


def test_decic_defaults_to_one_column():
    board, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[3G")
    parser.feed("\x1b['}")  # DECIC with no parameter -> 1
    assert _line(board) == "AB CDE"


def test_hpb_moves_cursor_left():
    board, parser = _term()
    parser.feed("\x1b[9G")  # column 9 (index 8)
    parser.feed("\x1b[3j")  # HPB 3
    assert board.cursor.x == 5


def test_vpb_moves_cursor_up():
    board, parser = _term()
    parser.feed("\x1b[5d")  # VPA to row 5 (index 4)
    parser.feed("\x1b[2k")  # VPB 2
    assert board.cursor.y == 2


def test_ctc_sets_and_clears_a_tab_stop_at_the_cursor():
    board, parser = _term()
    cursor = board.cursor
    parser.feed("\x1b[4G")  # column 4 (index 3)
    parser.feed("\x1b[0W")  # CTC 0 — set a tab stop here
    assert 3 in cursor.tab_stops
    parser.feed("\x1b[2W")  # CTC 2 — clear the tab stop here
    assert 3 not in cursor.tab_stops


def test_ctc_5_clears_all_tab_stops():
    board, parser = _term()
    parser.feed("\x1b[5W")  # CTC 5 — clear every tab stop
    assert board.cursor.tab_stops == set()


def test_decst8c_resets_tabs_every_eight_columns():
    board, parser = _term(width=30)
    cursor = board.cursor
    parser.feed("\x1b[5W")  # clear all tabs first
    assert cursor.tab_stops == set()
    parser.feed("\x1b[?5W")  # DECST8C — restore tabs every 8 columns
    assert cursor.tab_stops == {8, 16, 24}


def test_decscpp_changes_width_without_clearing_or_resetting_regions():
    board = Board(width=80, height=6)
    parser = Parser(board)
    parser.feed("hello")
    parser.feed("\x1b[2;5r\x1b[?69h\x1b[3;70s\x1b[4;5H")

    parser.feed("\x1b[132$|")

    assert board.width == 132
    assert board.blitter.current_buffer.get_line_text(0).startswith("hello")
    assert (board.cursor.x, board.cursor.y) == (4, 3)
    assert (board.blitter.scroll_top, board.blitter.scroll_bottom) == (1, 4)
    assert (board.blitter.left_margin, board.blitter.right_margin) == (2, 69)


def test_decscpp_expands_a_full_width_region_and_clamps_cursor_when_shrinking():
    board = Board(width=80, height=3)
    parser = Parser(board)

    parser.feed("\x1b[132$|")
    assert board.width == 132
    assert (board.blitter.left_margin, board.blitter.right_margin) == (0, 131)

    board.cursor.set_position(120, 1)
    parser.feed("\x1b[$|")  # omitted parameter defaults to 80
    assert board.width == 80
    assert (board.cursor.x, board.cursor.y) == (79, 1)
    assert (board.blitter.left_margin, board.blitter.right_margin) == (0, 79)


def test_decscpp_ignores_unsupported_column_counts():
    board, parser = _term()

    parser.feed("\x1b[100$|")

    assert board.width == 10


def test_decscpp_reports_changed_dimensions_to_the_pty():
    board = Board(width=80, height=3)
    board.pty = MemoryConnection()

    Parser(board).feed("\x1b[132$|")

    assert board.pty.resizes == [(3, 132)]
