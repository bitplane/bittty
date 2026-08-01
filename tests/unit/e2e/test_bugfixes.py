"""Regression tests for the Tier-0 correctness bugs."""

from bittty.parser import Parser
from bittty import Board


def _term():
    board = Board(width=20, height=10)
    return board, Parser(board)


def test_origin_mode_makes_cup_relative_to_the_scroll_region():
    board, parser = _term()
    parser.feed("\x1b[3;6r")  # DECSTBM: scroll region rows 3..6 (0-based 2..5)
    parser.feed("\x1b[?6h")  # DECOM on

    parser.feed("\x1b[1;1H")  # CUP to region-relative home
    assert (board.cursor.x, board.cursor.y) == (0, 2)  # top of region

    parser.feed("\x1b[99;1H")  # row far past the region -> clamped to region bottom
    assert board.cursor.y == 5

    # Without origin mode, CUP is absolute again.
    parser.feed("\x1b[?6l")
    parser.feed("\x1b[1;1H")
    assert (board.cursor.x, board.cursor.y) == (0, 0)


def test_decaln_fills_the_screen_and_does_not_leak_an_eight():
    board, parser = _term()
    parser.feed("\x1b#8")
    assert board.blitter.current_page.get_line_text(0) == "E" * 20  # filled, not a stray "8"
    assert "8" not in board.capture_pane()


def test_line_feed_below_scroll_region_still_advances():
    board, parser = _term()  # 20x10
    parser.feed("\x1b[1;5r")  # scroll region rows 1..5 (0-based 0..4)
    parser.feed("\x1b[8;1H")  # cursor below the region (row 8 -> 0-based 7)
    parser.feed("\n")
    assert board.cursor.y == 8  # advances, not stuck
    # ...and it does not scroll the region.
    parser.feed("\x1b[10;1H\n")  # at the very last row -> stays put
    assert board.cursor.y == 9


def test_decstbm_homes_the_cursor():
    board, parser = _term()
    parser.feed("\x1b[4;7H")  # move the cursor away from home
    parser.feed("\x1b[2;8r")  # DECSTBM
    assert (board.cursor.x, board.cursor.y) == (0, 0)


def test_scroll_region_keeps_content_outside_it():
    board, parser = _term()  # 20x10
    for row in range(1, 11):
        parser.feed(f"\x1b[{row};1Hrow{row}")
    parser.feed("\x1b[3;8r")  # region rows 3..8; rows 1,2,9,10 are fixed margins
    parser.feed("\x1b[8;1H")  # bottom of region
    parser.feed("\n\n")  # scroll the region twice
    buf = board.blitter.current_page
    for row in (1, 2, 9, 10):  # margins untouched
        assert buf.get_line_text(row - 1).startswith(f"row{row}")


def test_ansi_set_mode_7_does_not_toggle_autowrap():
    board, parser = _term()
    parser.feed("\x1b[?7l")  # DECRST private 7 -> autowrap off (the real control)
    assert board.modes.auto_wrap is False

    parser.feed("\x1b[7h")  # ANSI SM 7 (no '?') must NOT turn autowrap back on
    assert board.modes.auto_wrap is False
