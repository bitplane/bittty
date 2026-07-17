"""DECDHL/DECDWL/DECSWL per-line width and height attributes."""

from bittty import constants
from bittty.parser import Parser
from bittty import Board


def _term(width=10, height=4):
    terminal = Board(width=width, height=height)
    return terminal, Parser(terminal)


def _attr(terminal, y):
    return terminal.blitter.current_buffer.get_line_attribute(y)


def test_decdwl_sets_double_width_on_the_cursor_line():
    terminal, parser = _term()
    parser.feed("\x1b[3d")  # VPA to row 3 (index 2)
    parser.feed("\x1b#6")  # DECDWL
    assert _attr(terminal, 2) == constants.LINE_DOUBLE_WIDTH
    assert _attr(terminal, 0) == constants.LINE_SINGLE


def test_decdhl_top_and_bottom():
    terminal, parser = _term()
    parser.feed("\x1b#3")  # DECDHL top on row 0
    parser.feed("\x1b[2d")  # row 1
    parser.feed("\x1b#4")  # DECDHL bottom on row 1
    assert _attr(terminal, 0) == constants.LINE_DOUBLE_TOP
    assert _attr(terminal, 1) == constants.LINE_DOUBLE_BOTTOM


def test_decswl_resets_the_line_to_single():
    terminal, parser = _term()
    parser.feed("\x1b#6")  # DECDWL on row 0
    parser.feed("\x1b#5")  # DECSWL — back to single
    assert _attr(terminal, 0) == constants.LINE_SINGLE


def test_line_attribute_travels_with_the_line_on_scroll_up():
    terminal, parser = _term()
    parser.feed("\x1b[3d")  # row 2
    parser.feed("\x1b#6")  # DECDWL on row 2
    parser.feed("\x1b[S")  # SU 1 — everything scrolls up one row
    assert _attr(terminal, 1) == constants.LINE_DOUBLE_WIDTH
    assert _attr(terminal, 2) == constants.LINE_SINGLE


def test_line_attribute_travels_with_the_line_on_insert_line():
    terminal, parser = _term()
    parser.feed("\x1b[1d")  # row 0
    parser.feed("\x1b#6")  # DECDWL on row 0
    parser.feed("\x1b[L")  # IL 1 — insert a blank line at row 0, pushing it down
    assert _attr(terminal, 0) == constants.LINE_SINGLE  # the fresh blank line
    assert _attr(terminal, 1) == constants.LINE_DOUBLE_WIDTH  # the double line moved down


def test_ris_resets_all_line_attributes():
    terminal, parser = _term()
    parser.feed("\x1b#6")  # DECDWL on row 0
    parser.feed("\x1bc")  # RIS
    assert _attr(terminal, 0) == constants.LINE_SINGLE


def test_resize_keeps_attributes_aligned_with_rows():
    terminal, parser = _term(height=4)
    parser.feed("\x1b[2d")  # row 1
    parser.feed("\x1b#6")  # DECDWL on row 1
    terminal.resize(10, 6)  # grow
    assert _attr(terminal, 1) == constants.LINE_DOUBLE_WIDTH
    assert _attr(terminal, 5) == constants.LINE_SINGLE
