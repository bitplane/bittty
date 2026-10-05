"""Page memory (VT510): NP, PP, PPA, PPR, PPB, DECPCCM, and the reports that carry a page.

Behaviour from the VT510 reference manual: 3 pages of 24 lines, 2 of 25 or 36, else 1.
xterm has one page; its replies (DECRQDE, and paging ignored) are captured from xterm 407.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import LINUX, VT510, XTERM


def _run(sequence, model=VT510, height=24):
    board = Board(width=20, height=height, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence.encode())
    return board, wire


def _pages(board):
    return [page.get_line_text(0).rstrip() for page in board.blitter.pages]


def _where(board):
    return board.blitter.page + 1, board.cursor.y + 1, board.cursor.display_x + 1


@pytest.mark.parametrize(("height", "count"), [(24, 3), (25, 2), (36, 2), (48, 1), (10, 1)])
def test_lines_per_page_decide_how_many_pages(height, count):
    board, _ = _run("", height=height)
    assert len(board.blitter.pages) == count


@pytest.mark.parametrize(
    ("sequence", "where"),
    [
        ("\x1b[3;5H\x1b[U", (2, 1, 1)),  # NP: the next page, at home
        ("\x1b[0U", (2, 1, 1)),  # 0 is 1
        ("\x1b[2U", (3, 1, 1)),
        ("\x1b[9U", (3, 1, 1)),  # stops at the last page
        ("\x1b[2U\x1b[3;5H\x1b[V", (2, 1, 1)),  # PP: the preceding page, at home
        ("\x1b[U\x1b[9V", (1, 1, 1)),  # stops at the first
        ("\x1b[3;5H\x1b[3 P", (3, 3, 5)),  # PPA: the same row and column on page Pn
        ("\x1b[3;5H\x1b[9 P", (3, 3, 5)),
        ("\x1b[U\x1b[3;5H\x1b[ P", (1, 3, 5)),  # page 1 by default
        ("\x1b[3;5H\x1b[ Q", (2, 3, 5)),  # PPR: forward, same position
        ("\x1b[3;5H\x1b[5 Q", (3, 3, 5)),
        ("\x1b[3 P\x1b[3;5H\x1b[ R", (2, 3, 5)),  # PPB: backward, same position
        ("\x1b[3 P\x1b[3;5H\x1b[5 R", (1, 3, 5)),
        ("\x1b[5;10r\x1b[?6h\x1b[2;2H\x1b[U", (2, 5, 1)),  # home honours origin mode
    ],
)
def test_moving_between_pages(sequence, where):
    board, _ = _run(sequence)
    assert _where(board) == where


def test_each_page_keeps_its_own_text():
    board, _ = _run("one\x1b[Utwo\x1b[Uthree\x1b[1 P\x1b[Hfour")
    assert _pages(board) == ["four", "two", "three"]


def test_erasing_touches_only_the_cursor_page():
    board, _ = _run("one\x1b[Utwo\x1b[2J")
    assert _pages(board) == ["one", "", ""]


def test_one_page_ignores_paging():
    board, _ = _run("\x1b[3;5H\x1b[Ux", height=48)
    assert _where(board) == (1, 3, 6)


@pytest.mark.parametrize("model", [XTERM, LINUX])
def test_a_terminal_without_page_memory_ignores_paging(model):
    """xterm 407 leaves the cursor where it was for NP, PP and PPA."""
    board, _ = _run("\x1b[5;5H\x1b[U\x1b[V\x1b[2 P", model)
    assert (board.cursor.y, board.cursor.x) == (4, 4)


# --- DECPCCM: which page the display shows --- #


def test_the_display_follows_the_cursor_by_default():
    board, _ = _run("one\x1b[Utwo")
    assert board.blitter.main_page is board.blitter.pages[1]
    assert board.blitter.cursor_on_display


def test_an_uncoupled_cursor_leaves_the_display_behind():
    board, _ = _run("one\x1b[?64l\x1b[Utwo")
    assert board.capture_text() == "one"
    assert not board.blitter.cursor_on_display


def test_coupling_again_brings_the_cursor_page_into_view():
    board, _ = _run("one\x1b[?64l\x1b[Utwo\x1b[?64h")
    assert board.capture_text() == "two"


@pytest.mark.parametrize(("sequence", "status"), [("", 1), ("\x1b[?64l", 2)])
def test_decrqm_reports_page_coupling(sequence, status):
    _, wire = _run(sequence + "\x1b[?64$p")
    assert wire.data == [f"\x1b[?64;{status}$y"]


# --- reports and rectangles that name a page --- #


@pytest.mark.parametrize(
    ("sequence", "reply", "model"),
    [
        ("", '\x1b[24;20;1;1;1"w', XTERM),
        ("\x1b[U", '\x1b[24;20;1;1;2"w', VT510),
        ("\x1b[?64l\x1b[U", '\x1b[24;20;1;1;1"w', VT510),  # the displayed page, not the cursor's
    ],
)
def test_decrqde_reports_the_displayed_extent(sequence, reply, model):
    _, wire = _run(sequence + '\x1b["v', model)
    assert wire.data == [reply]


def test_a_terminal_without_decrqde_does_not_answer():
    _, wire = _run('\x1b["v', LINUX)
    assert wire.data == []


def test_deccir_reports_the_cursor_page():
    _, wire = _run("\x1b[2U\x1b[1$w")
    assert wire.data[0].startswith("\x1bP1$u1;1;3;")


def test_decrsps_restores_the_cursor_page():
    board, _ = _run("\x1bP1$t3;5;2;@;@;@;0;2;@;BBBB\x1b\\")
    assert _where(board) == (2, 3, 5)


def test_deccra_copies_between_pages():
    board, _ = _run("abc\x1b[1;1;1;3;1;1;1;3$v")
    assert _pages(board) == ["abc", "", "abc"]


def test_deccra_pages_default_to_the_first():
    board, _ = _run("abc\x1b[U\x1b[1;1;1;3;;1;4$v")
    assert _pages(board) == ["abcabc", "", ""]


def test_decrqcra_sums_the_named_page():
    board, wire = _run("\x1b[Uab\x1b[1;2;1;1;1;2*y\x1b[1;1;1;1;1;2*y")
    ab = -(ord("a") + ord("b")) & 0xFFFF
    blanks = -(2 * 0x20) & 0xFFFF
    assert wire.data == [f"\x1bP1!~{ab:04X}\x1b\\", f"\x1bP1!~{blanks:04X}\x1b\\"]


def test_ris_clears_every_page_and_returns_to_the_first():
    board, _ = _run("one\x1b[Utwo\x1bc")
    assert _pages(board) == ["", "", ""] and _where(board) == (1, 1, 1)


def test_resizing_changes_the_page_count_and_keeps_the_cursor_in_memory():
    board, _ = _run("one\x1b[2Uthree")
    board.resize(20, 25)
    assert len(board.blitter.pages) == 2 and board.blitter.page == 1
    assert board.blitter.main_page is board.blitter.pages[1]
