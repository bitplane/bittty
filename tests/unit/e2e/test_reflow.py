"""Reflow on resize: soft-wrapped lines re-wrap to the new width, and the cursor keeps its place.

gnome (VTE) and kitty always reflow the primary screen; bittty does under Contour's text reflow
mode (2028), on by default; xterm and the DEC terminals cut lines at the new width. The
alternate screen is never reflowed.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import BITTTY, GNOME, KITTY, VT510, XTERM


def _board(model=BITTTY, width=10, height=4):
    board = Board(width=width, height=height, model=model)
    board.host.attach(MemoryConnection())
    return board


def _screen(board):
    page = board.blitter.current_page
    return [page.get_line_text(y).rstrip() for y in range(page.height)], (board.cursor.y, board.cursor.x)


@pytest.mark.parametrize("model", [BITTTY, GNOME, KITTY])
def test_narrowing_rewraps(model):
    board = _board(model)
    board.feed_host_data("abcdefgh\r\nxy")
    board.resize(4, 4)
    assert _screen(board) == (["abcd", "efgh", "xy", ""], (2, 2))


def test_widening_joins_what_wrapped():
    board = _board()
    board.feed_host_data("abcdefghijklm\r\nxy")
    board.resize(20, 4)
    assert _screen(board) == (["abcdefghijklm", "xy", "", ""], (1, 2))


def test_hard_line_breaks_stay():
    board = _board()
    board.feed_host_data("ab\r\ncd")
    board.resize(20, 4)
    assert _screen(board) == (["ab", "cd", "", ""], (1, 2))


def test_rows_that_no_longer_fit_leave_at_the_top():
    board = _board(height=3)
    board.feed_host_data("one\r\nabcdefgh\r\nxy")
    board.resize(4, 3)
    assert _screen(board) == (["abcd", "efgh", "xy"], (2, 2))


def test_the_cursor_mid_line_keeps_its_character():
    board = _board()
    board.feed_host_data("abcdefghij" + "klm\x1b[1;7H")  # the cursor on "g"
    board.resize(4, 4)
    lines, (y, x) = _screen(board)
    assert lines == ["abcd", "efgh", "ijkl", "m"] and board.blitter.current_page.get_line_text(y)[x] == "g"


def test_wide_characters_are_not_split():
    board = _board()
    board.feed_host_data("abc中def")
    board.resize(4, 4)
    assert _screen(board)[0] == ["abc", "中de", "f", ""]


def test_the_rewrapped_rows_still_wrap():
    board = _board()
    board.feed_host_data("abcdefgh")
    board.resize(4, 4)
    board.resize(10, 4)
    assert _screen(board)[0] == ["abcdefgh", "", "", ""]


@pytest.mark.parametrize("model", [XTERM, VT510])
def test_terminals_that_cut(model):
    board = _board(model)
    board.feed_host_data("abcdefgh\r\nxy")
    board.resize(4, 4)
    assert _screen(board)[0] == ["abcd", "xy", "", ""]


def test_the_mode_turns_it_off():
    board = _board()
    board.feed_host_data("\x1b[?2028labcdefgh\r\nxy")
    board.resize(4, 4)
    assert _screen(board)[0] == ["abcd", "xy", "", ""]


def test_decrqm():
    board = _board()
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data("\x1b[?2028$p\x1b[?2028l\x1b[?2028$p")
    assert wire.data == ["\x1b[?2028;1$y", "\x1b[?2028;2$y"]


def test_the_alternate_screen_is_cut():
    board = _board()
    board.feed_host_data("\x1b[?1049habcdefgh")
    board.resize(4, 4)
    assert _screen(board)[0] == ["abcd", "", "", ""]
