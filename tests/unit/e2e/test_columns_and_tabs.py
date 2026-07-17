"""DECIC/DECDC column edits, HPB/VPB position-backward, and CTC/DECST8C tab control."""

from bittty.parser import Parser
from bittty import Board


def _term(width=10, height=6):
    terminal = Board(width=width, height=height)
    return terminal, Parser(terminal)


def _line(terminal, y=0):
    return terminal.blitter.current_buffer.get_line_text(y).rstrip()


def test_decic_inserts_columns_at_cursor():
    terminal, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[3G")  # cursor to column 3 (index 2)
    parser.feed("\x1b[2'}")  # DECIC 2 — insert two blank columns
    assert _line(terminal) == "AB  CDE"


def test_decdc_deletes_columns_at_cursor():
    terminal, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[2G")  # cursor to column 2 (index 1)
    parser.feed("\x1b[2'~")  # DECDC 2 — delete two columns
    assert _line(terminal) == "ADE"


def test_decic_defaults_to_one_column():
    terminal, parser = _term()
    parser.feed("ABCDE")
    parser.feed("\x1b[3G")
    parser.feed("\x1b['}")  # DECIC with no parameter -> 1
    assert _line(terminal) == "AB CDE"


def test_hpb_moves_cursor_left():
    terminal, parser = _term()
    parser.feed("\x1b[9G")  # column 9 (index 8)
    parser.feed("\x1b[3j")  # HPB 3
    assert terminal.cursor.x == 5


def test_vpb_moves_cursor_up():
    terminal, parser = _term()
    parser.feed("\x1b[5d")  # VPA to row 5 (index 4)
    parser.feed("\x1b[2k")  # VPB 2
    assert terminal.cursor.y == 2


def test_ctc_sets_and_clears_a_tab_stop_at_the_cursor():
    terminal, parser = _term()
    cursor = terminal.cursor
    parser.feed("\x1b[4G")  # column 4 (index 3)
    parser.feed("\x1b[0W")  # CTC 0 — set a tab stop here
    assert 3 in cursor.tab_stops
    parser.feed("\x1b[2W")  # CTC 2 — clear the tab stop here
    assert 3 not in cursor.tab_stops


def test_ctc_5_clears_all_tab_stops():
    terminal, parser = _term()
    parser.feed("\x1b[5W")  # CTC 5 — clear every tab stop
    assert terminal.cursor.tab_stops == set()


def test_decst8c_resets_tabs_every_eight_columns():
    terminal, parser = _term(width=30)
    cursor = terminal.cursor
    parser.feed("\x1b[5W")  # clear all tabs first
    assert cursor.tab_stops == set()
    parser.feed("\x1b[?5W")  # DECST8C — restore tabs every 8 columns
    assert cursor.tab_stops == {8, 16, 24}
