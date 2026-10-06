"""Scrollback: lines kept after they scroll off the board, laid out at any width.

A store numbers its lines for life, lays them out a line to ceil(cells / width)
rows (an empty line one), and forgets its oldest past a budget of cells. A
terminal given one keeps the rows the board sends it, and can show history above
the screen, held still while output arrives.
"""

import os

import pytest

from bittty import Board, MemoryConnection
from bittty.style import Style
from bittty.terminals import StdioTerminal, Terminal
from bittty.terminals.scrollback import MemoryScrollback, ScrollbackLine, rows_of
from bittty.video import CONTINUATION, WideHead

PLAIN = Style()
RED = Style(fg="red")
BLUE_BACKGROUND = Style(bg="blue")


def _cells(text, style=PLAIN):
    return [(style, char) for char in text]


def _line(text, style=PLAIN):
    return ScrollbackLine.of(_cells(text, style))


def _text(rows):
    return ["".join(char for _, char in row).rstrip() for row in rows]


def _store(*lines, max_cells=1000):
    store = MemoryScrollback(max_cells)
    for text in lines:
        store.append(_line(text))
    return store


# --- a line --- #


def test_a_line_is_its_text_and_each_cells_style():
    line = ScrollbackLine.of(_cells("ab", RED) + _cells("c"))
    assert (line.text, line.styles, line.shape) == ("abc", (RED, RED, PLAIN), None)
    assert line.runs == [(0, RED), (2, PLAIN)]
    assert len(line) == 3


def test_a_wide_glyph_and_a_cluster_give_the_line_a_shape():
    cells = [(PLAIN, WideHead("中")), (PLAIN, CONTINUATION), (PLAIN, "é"), (PLAIN, "x")]
    line = ScrollbackLine.of(cells)
    assert (line.text, line.shape) == ("中éx", (1, 0, 2, 1))


@pytest.mark.parametrize(
    "cells",
    [
        _cells("plain", RED) + _cells(" text"),
        [(RED, WideHead("中")), (RED, CONTINUATION), (PLAIN, "é"), (PLAIN, "x")],
    ],
    ids=["regular", "shaped"],
)
def test_a_line_gives_back_the_cells_it_was_made_of(cells):
    back = ScrollbackLine.of(cells).cells(0, len(cells))
    assert back == list(cells)
    assert [type(char) for _, char in back] == [type(char) for _, char in cells]


def test_a_wide_glyph_keeps_its_head_marker():
    line = ScrollbackLine.of([(PLAIN, WideHead("中")), (PLAIN, CONTINUATION)])
    assert isinstance(line.cells(0, 2)[0][1], WideHead)


def test_a_wide_glyph_cut_by_either_end_of_a_stretch_is_blank_in_its_style():
    line = ScrollbackLine.of(_cells("a") + [(RED, WideHead("中")), (RED, CONTINUATION)] + _cells("b"))
    assert line.cells(0, 2) == [(PLAIN, "a"), (RED, " ")]
    assert line.cells(2, 4) == [(RED, " "), (PLAIN, "b")]


def test_trimming_drops_trailing_unstyled_blanks_only():
    page_blank = (Style(), " ")  # a different but equal style object, as a page holds
    line = ScrollbackLine.of(_cells("a b") + [page_blank] * 5, trim=True)
    assert (line.text, len(line)) == ("a b", 3)


@pytest.mark.parametrize("unstyled", ["", "  "], ids=["alone", "then-unstyled"])
def test_trimming_keeps_blanks_with_a_background(unstyled):
    line = ScrollbackLine.of(_cells("ab") + _cells("  ", BLUE_BACKGROUND) + _cells(unstyled), trim=True)
    assert (line.text, line.styles) == ("ab  ", (PLAIN, PLAIN, BLUE_BACKGROUND, BLUE_BACKGROUND))


def test_trimming_a_blank_row_leaves_an_empty_line():
    assert len(ScrollbackLine.of(_cells("    "), trim=True)) == 0


def test_trimming_keeps_a_wide_glyph_and_its_tail():
    line = ScrollbackLine.of([(PLAIN, WideHead("中")), (PLAIN, CONTINUATION)] + _cells("  "), trim=True)
    assert (line.text, line.shape) == ("中", (1, 0))


def test_rows_joined_into_a_line_keep_their_styles_and_shapes():
    line = ScrollbackLine.join([_line("ab", RED), ScrollbackLine.of([(PLAIN, WideHead("中")), (PLAIN, CONTINUATION)])])
    assert (line.text, line.styles, line.shape) == ("ab中", (RED, RED, PLAIN, PLAIN), (1, 1, 1, 0))


def test_a_line_takes_ceil_cells_over_width_rows_and_an_empty_one_takes_one():
    assert [rows_of(cells, 4) for cells in (0, 1, 4, 5, 8, 9)] == [1, 1, 1, 2, 2, 3]


# --- a memory store --- #


def test_lines_are_numbered_from_zero():
    store = _store("one", "two")
    assert (store.first, store.end) == (0, 2)
    assert store.line(1).text == "two"


def test_a_view_lays_the_lines_out_at_its_width():
    view = _store("abcdefghij", "", "xy").width(4)
    assert len(view) == 5
    assert _text(view) == ["abcd", "efgh", "ij", "", "xy"]


def test_a_view_row_is_exactly_its_width_wide():
    assert len(_store("ab").width(6)[0]) == 6


def test_a_view_says_which_line_a_row_is_and_where_a_line_starts():
    view = _store("abcdefghij", "", "xy").width(4)
    assert [view.line_at(row) for row in range(5)] == [(0, 0), (0, 1), (0, 2), (1, 0), (2, 0)]
    assert [view.row_for(line) for line in range(3)] == [0, 3, 4]


def test_a_view_follows_the_store():
    store = _store("one")
    view = store.width(10)
    store.append(_line("two"))
    assert _text(view) == ["one", "two"]


def test_wrapped_rows_arrive_as_one_line():
    store = MemoryScrollback()
    store.append(_line("abcd"), wrapped=True)
    store.append(_line("ef"))
    assert store.end == 1
    assert _text(store.width(3)) == ["abc", "def"]


def test_a_line_still_arriving_is_held_and_shown():
    store = _store("done")
    store.append(_line("abcd"), wrapped=True)
    assert store.end == 2
    view = store.width(4)
    assert _text(view) == ["done", "abcd"]
    assert view.line_at(1) == (1, 0)
    store.append(_line("ef"), wrapped=True)
    assert _text(view) == ["done", "abcd", "ef"]


def test_the_oldest_lines_go_first_past_the_budget_each_costing_one_more_than_its_cells():
    store = _store("aaaa", "bbbb", "cccc", max_cells=10)
    assert (store.first, store.end) == (1, 3)
    assert _text(store.width(10)) == ["bbbb", "cccc"]


def test_empty_lines_count_against_the_budget():
    store = _store(*[""] * 20, max_cells=10)
    assert store.end - store.first == 10


def test_a_line_longer_than_the_budget_keeps_its_newest_rows():
    store = MemoryScrollback(10)
    for row in ("aaaa", "bbbb", "cccc", "dddd"):
        store.append(_line(row), wrapped=True)
    assert _text(store.width(4)) == ["cccc", "dddd"]


def test_a_row_wider_than_the_whole_budget_is_still_held():
    store = MemoryScrollback(3)
    store.append(_line("abcd"), wrapped=True)
    assert _text(store.width(4)) == ["abcd"]


def test_numbering_carries_on_after_eviction():
    store = MemoryScrollback(4)
    view = store.width(1)
    for text in "abcdefgh":
        store.append(_line(text))
    assert _text(view) == ["g", "h"]
    assert (store.first, store.end) == (6, 8)
    assert view.line_at(0) == (6, 0)
    assert view.row_for(7) == 1


def test_clearing_forgets_everything_and_numbering_carries_on():
    store = _store("one", "two")
    view = store.width(10)
    store.clear()
    assert (store.first, store.end, len(view)) == (2, 2, 0)
    store.append(_line("three"))
    assert view.line_at(0) == (2, 0)
    assert _text(view) == ["three"]


def test_many_widths_viewed_in_turn_each_lay_out_correctly():
    store = _store("abcdefghijkl")
    assert [len(store.width(columns)) for columns in range(1, 13)] == [12, 6, 4, 3, 3, 2, 2, 2, 2, 2, 2, 1]
    assert len(store.width(1)) == 12


def test_a_view_kept_while_many_other_widths_are_viewed_still_follows_the_store():
    store = _store("abcdef")
    view = store.width(2)
    for columns in range(3, 10):
        store.width(columns)
    store.append(_line("gh"))
    assert _text(view) == ["ab", "cd", "ef", "gh"]


def test_a_view_past_its_last_row_raises_index_error():
    view = _store("one").width(10)
    with pytest.raises(IndexError):
        view[1]


# --- a terminal keeping scrollback --- #


def _terminal(width=10, height=3, scrollback=None):
    board = Board(width=width, height=height)
    board.host.attach(MemoryConnection())
    terminal = Terminal(board, scrollback if scrollback is not None else MemoryScrollback())
    terminal.attach()
    return board, terminal


def test_a_terminal_given_a_store_keeps_scrollback():
    board, terminal = _terminal()
    assert terminal.keeps_scrollback is True
    board.feed_host_data(b"one\r\ntwo\r\nthree\r\nfour")
    assert _text(terminal.scrollback.width(10)) == ["one"]


def test_a_terminal_keeps_lines_wrapped_across_rows_as_one():
    board, terminal = _terminal(width=4)
    board.feed_host_data(b"abcdef\r\n\r\n\r\n")
    assert terminal.scrollback.line(0).text == "abcdef"


def test_a_line_kept_loses_its_trailing_blanks():
    board, terminal = _terminal()
    board.feed_host_data(b"hi\r\n\r\n\r\n")
    assert len(terminal.scrollback.line(0)) == 2


def test_the_view_starts_live():
    board, terminal = _terminal()
    board.feed_host_data(b"1\r\n2\r\n3\r\n4\r\n5")
    assert terminal.view_offset() == 0
    assert _text(terminal.view_rows()) == ["3", "4", "5"]


def test_scrolling_back_shows_history_above_the_screen():
    board, terminal = _terminal()
    board.feed_host_data(b"1\r\n2\r\n3\r\n4\r\n5")
    terminal.scroll_view(-1)
    assert terminal.view_offset() == 1
    assert _text(terminal.view_rows()) == ["2", "3", "4"]


def test_scrolling_back_stops_at_the_oldest_row_and_forward_at_the_live_screen():
    board, terminal = _terminal()
    board.feed_host_data(b"1\r\n2\r\n3\r\n4\r\n5")
    terminal.scroll_view(-10)
    assert _text(terminal.view_rows()) == ["1", "2", "3"]
    terminal.scroll_view(10)
    assert terminal.view_top is None


def test_the_view_holds_still_as_output_arrives():
    board, terminal = _terminal()
    board.feed_host_data(b"1\r\n2\r\n3\r\n4\r\n5")
    terminal.scroll_view(-2)
    board.feed_host_data(b"\r\n6\r\n7")
    assert _text(terminal.view_rows()) == ["1", "2", "3"]


def test_the_view_holds_its_line_as_the_width_changes():
    board, terminal = _terminal(width=4)
    board.feed_host_data(b"abcdefgh\r\nx\r\ny\r\nz\r\n")
    terminal.scroll_view(-1)
    assert terminal.view_top == (1, 0)
    board.display.resize(2, 3)
    assert _text(terminal.view_rows())[0] == "x"


def test_a_view_on_lines_since_forgotten_shows_the_oldest_held():
    board, terminal = _terminal(scrollback=MemoryScrollback(6))
    board.feed_host_data(b"1\r\n2\r\n3\r\n4\r\n5")
    terminal.scroll_view(-2)
    board.feed_host_data(b"\r\n6\r\n7\r\n8")
    assert _text(terminal.view_rows())[0] == str(terminal.scrollback.first + 1)


def test_scroll_to_bottom_returns_to_the_live_screen():
    board, terminal = _terminal()
    board.feed_host_data(b"1\r\n2\r\n3\r\n4\r\n5")
    terminal.scroll_view(-1)
    terminal.scroll_to_bottom()
    assert terminal.view_top is None


def test_ed_3_clears_the_store_and_returns_to_the_live_screen():
    board, terminal = _terminal()
    board.feed_host_data(b"1\r\n2\r\n3\r\n4\r\n5")
    terminal.scroll_view(-1)
    board.feed_host_data(b"\x1b[3J")
    assert terminal.view_top is None
    assert len(terminal.scrollback.width(10)) == 0


@pytest.mark.parametrize("back", [lambda t: t.scroll_view(1), Terminal.scroll_to_bottom], ids=["scroll", "bottom"])
def test_coming_back_to_the_live_screen_damages_every_row(back):
    board, terminal = _terminal()
    board.feed_host_data(b"1\r\n2\r\n3\r\n4\r\n5")
    terminal.damaged_rows()
    terminal.scroll_view(-1)
    back(terminal)
    assert list(terminal.damaged_rows()) == [0, 1, 2]


# --- the reference terminal --- #


@pytest.fixture
def stdio(monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size", lambda: os.terminal_size((10, 3)))
    board = Board(width=10, height=3)
    wire = MemoryConnection()
    board.host.attach(wire)
    terminal = StdioTerminal(board, MemoryScrollback())
    board.feed_host_data(b"1\r\n2\r\n3\r\n4\r\n5\r\n6")
    return terminal, wire


def test_shift_page_up_pages_back_keeping_a_row_and_page_down_pages_forward(stdio):
    terminal, wire = stdio
    terminal.handle_input(b"\x1b[5;2~")
    assert terminal.view_offset() == 2
    terminal.handle_input(b"\x1b[6;2~")
    assert terminal.view_top is None
    assert wire.data == []


def test_a_key_release_does_not_page(stdio):
    terminal, wire = stdio
    terminal.handle_input(b"\x1b[5;2:3~")
    assert terminal.view_top is None
    assert wire.data == []


@pytest.mark.parametrize("typed", [b"x", b"\x1b[A"], ids=["text", "key"])
def test_typing_returns_to_the_live_screen(stdio, typed):
    terminal, wire = stdio
    terminal.handle_input(b"\x1b[5;2~")
    terminal.handle_input(typed)
    assert terminal.view_top is None
    assert wire.data


def test_without_a_store_shift_page_up_goes_to_the_child(monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size", lambda: os.terminal_size((10, 3)))
    board = Board(width=10, height=3)
    wire = MemoryConnection()
    board.host.attach(wire)
    StdioTerminal(board).handle_input(b"\x1b[5;2~")
    assert "".join(wire.data) == "\x1b[5;2~"


def test_scrolled_back_the_reference_terminal_paints_history_and_moves_the_cursor_down(stdio, capsys):
    terminal, _ = stdio
    terminal.handle_input(b"\x1b[5;2~")
    capsys.readouterr()
    terminal.render_screen()
    out = capsys.readouterr().out
    assert "\x1b[1H2" in out and "\x1b[3H4" in out
    assert "\x1b[?25h" not in out  # the cursor's row is below the view


def test_scrolled_back_one_row_the_cursor_is_drawn_a_row_lower(stdio, capsys):
    terminal, _ = stdio
    terminal.board.feed_host_data(b"\x1b[2;2H")
    terminal.scroll_view(-1)
    capsys.readouterr()
    terminal.render_screen()
    assert capsys.readouterr().out.endswith("\x1b[3;2H\x1b[?25h")
