"""The terminal's side of the seam: the screen it pulls, the events it is pushed.

Push what would otherwise be lost (rows leaving the top, the child going away);
pull what is still there (the page, the cursor), on the terminal's own cadence.
"""

import asyncio
import io
import os
import sys

import pytest

from bittty import Board, MemoryConnection
from bittty.connections import Screen
from bittty.model import VT510
from bittty.present import ChildExited, RowsScrolledOff, ScreenChanged, ScrollbackCleared
from bittty.terminals import StdioTerminal, Terminal


class Recorder:
    keeps_scrollback = True

    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)

    def of(self, kind):
        return [event for event in self.events if isinstance(event, kind)]


def _board(width=10, height=3, **kwargs):
    board = Board(width=width, height=height, **kwargs)
    board.host.attach(MemoryConnection())
    recorder = Recorder()
    board.display.attach(recorder)
    return board, recorder


def _text(lines):
    return ["".join(char for _, char in line.cells).rstrip() for line in lines]


def _scrolled(recorder):
    return [_text(event.lines) for event in recorder.of(RowsScrolledOff)]


# --- the screen, pulled --- #


def test_the_display_port_is_a_screen():
    board, _ = _board()
    assert isinstance(board.display, Screen)
    assert (board.display.width, board.display.height) == (10, 3)
    assert board.display.page is board.blitter.main_page


def test_the_cursor_is_where_to_draw_it_or_none():
    board, _ = _board()
    board.feed_host_data(b"\x1b[2;4H")
    assert board.display.cursor == (3, 1)
    board.feed_host_data(b"\x1b[?25l")
    assert board.display.cursor is None


def test_there_is_no_cursor_to_draw_while_the_status_line_is_written():
    board, _ = _board(model=VT510)
    board.feed_host_data(b"\x1b[2$~\x1b[1$}")
    assert board.display.cursor is None


def test_the_port_says_when_a_lone_escape_is_a_key():
    board, _ = _board()
    assert board.display.escape_is_key is False
    board.feed_host_data(b"\x1b[?7727h")
    assert board.display.escape_is_key is True


def test_damaged_rows_are_everything_first_then_only_what_changed():
    board, _ = _board()
    terminal = Terminal(board)
    assert list(terminal.damaged_rows()) == [0, 1, 2]
    assert list(terminal.damaged_rows()) == []
    board.feed_host_data(b"\x1b[2Hx")
    assert list(terminal.damaged_rows()) == [1]


def test_a_page_flip_damages_every_row():
    board, _ = _board()
    terminal = Terminal(board)
    terminal.damaged_rows()
    board.feed_host_data(b"\x1b[?1049h")
    assert list(terminal.damaged_rows()) == [0, 1, 2]


# --- the screen changed --- #


def test_each_chunk_of_host_output_says_the_screen_changed():
    board, recorder = _board()
    board.feed_host_data(b"one")
    board.feed_host_data(b"two")
    assert recorder.of(ScreenChanged) == [ScreenChanged(), ScreenChanged()]


def test_local_echo_says_the_screen_changed():
    board, recorder = _board()
    board.feed_host_data(b"\x1b[12l")  # SRM reset: local echo on
    recorder.events.clear()
    board.input_text("hi")
    assert board.capture_text() == "hi"
    assert recorder.of(ScreenChanged)


# --- rows leaving the top --- #


def test_a_terminal_that_keeps_no_scrollback_is_sent_no_rows():
    board, recorder = _board()
    recorder.keeps_scrollback = False
    board.feed_host_data(b"one\r\ntwo\r\nthree\r\nfour")
    assert _scrolled(recorder) == []


def test_the_base_terminal_keeps_no_scrollback():
    assert Terminal.keeps_scrollback is False


def test_rows_scrolled_off_the_top_are_sent_with_their_cells_oldest_first():
    board, recorder = _board()
    board.feed_host_data(b"one\r\ntwo\r\nthree\r\nfour\r\nfive")
    assert _scrolled(recorder) == [["one"], ["two"]]
    assert board.capture_text() == "three\nfour\nfive"


def test_a_scroll_up_sends_every_row_it_removes():
    board, recorder = _board()
    board.feed_host_data(b"a\r\nb\r\nc\x1b[2S")
    assert _scrolled(recorder) == [["a", "b"]]


def test_a_wrapped_row_says_so():
    board, recorder = _board(width=4)
    board.feed_host_data(b"abcdefg\r\n\r\n\r\n")
    (first, second) = (line for event in recorder.of(RowsScrolledOff) for line in event.lines)
    assert (first.wrapped, second.wrapped) == (True, False)


def test_a_region_at_the_top_scrolls_into_history_and_one_below_it_does_not():
    board, recorder = _board(height=4)
    board.feed_host_data(b"top\x1b[1;2r\x1b[2Hx\n")
    assert _scrolled(recorder) == [["top"]]
    recorder.events.clear()
    board.feed_host_data(b"\x1b[2;3r\x1b[3Hy\n")
    assert _scrolled(recorder) == []


def test_the_alternate_screen_never_scrolls_into_history():
    board, recorder = _board()
    board.feed_host_data(b"\x1b[?1049h1\r\n2\r\n3\r\n4")
    assert _scrolled(recorder) == []


@pytest.mark.parametrize("margins", [b"2;10", b"1;5"], ids=["left", "right"])
def test_a_margin_box_narrower_than_the_page_does_not_scroll_into_history(margins):
    board, recorder = _board()
    board.feed_host_data(b"\x1b[?69h\x1b[" + margins + b"s\x1b[3;3Hx\n")
    assert _scrolled(recorder) == []


def test_a_scroll_down_sends_nothing():
    board, recorder = _board()
    board.feed_host_data(b"a\x1b[2T")
    assert _scrolled(recorder) == []


def test_rows_a_narrowing_reflow_cuts_from_the_top_are_sent():
    board, recorder = _board(width=6, height=2)
    board.feed_host_data(b"abcdef\r\nxy")
    board.resize(3, 2)
    assert _scrolled(recorder) == [["abc"]]
    assert board.capture_text() == "def\nxy"


def test_ed_3_asks_for_the_scrollback_to_be_cleared_and_leaves_the_screen():
    board, recorder = _board()
    board.feed_host_data(b"keep\x1b[3J")
    assert recorder.of(ScrollbackCleared) == [ScrollbackCleared()]
    assert board.capture_text() == "keep"


# --- the child going away --- #


async def _until(condition) -> None:
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


@pytest.mark.asyncio
async def test_a_stream_reaching_its_end_is_a_child_exit_with_no_status():
    board = Board(width=10, height=2, stdin=io.BufferedReader(io.BytesIO(b"bye")), stdout=io.BytesIO())
    recorder = Recorder()
    board.display.attach(recorder)
    await board.start_process()
    await _until(lambda: recorder.of(ChildExited))
    assert recorder.of(ChildExited) == [ChildExited(None)]
    assert board.capture_text() == "bye"
    assert board.pty is None


@pytest.mark.skipif(sys.platform == "win32", reason="needs a POSIX shell")
@pytest.mark.asyncio
async def test_a_child_that_exits_reports_its_status():
    board = Board(command="sh -c 'exit 3'", width=10, height=2)
    recorder = Recorder()
    board.display.attach(recorder)
    await board.start_process()
    await _until(lambda: recorder.of(ChildExited))
    assert recorder.of(ChildExited) == [ChildExited(3)]


@pytest.mark.asyncio
async def test_stopping_the_child_is_not_an_exit():
    read, write = os.pipe()
    board = Board(width=10, height=2, stdin=os.fdopen(read, "rb"), stdout=io.BytesIO())
    recorder = Recorder()
    board.display.attach(recorder)
    await board.start_process()
    board.stop_process()
    await asyncio.sleep(0.05)
    os.close(write)
    assert recorder.of(ChildExited) == []


# --- a terminal given a board --- #


def test_a_terminal_can_be_given_a_board_and_fits_it_to_the_venue(monkeypatch):
    monkeypatch.setattr("shutil.get_terminal_size", lambda: os.terminal_size((30, 7)))
    board = Board(width=10, height=3)
    terminal = StdioTerminal(board)
    assert terminal.board is board
    assert board.display.terminal is terminal
    assert (board.width, board.height) == (30, 7)


def test_a_given_board_already_on_a_host_is_not_given_another_child():
    board = Board(width=10, height=3)
    wire = MemoryConnection()
    board.host.attach(wire)
    terminal = StdioTerminal(board)
    asyncio.run(terminal.start_host())
    assert board.process is None
    assert board.host.connection is wire


def test_the_reference_terminal_stops_when_the_child_exits():
    terminal = StdioTerminal()
    terminal.present(ChildExited(0))
    assert terminal.running is False


def test_the_reference_terminal_repaints_when_the_screen_changed():
    terminal = StdioTerminal()
    terminal.dirty = False
    terminal.board.feed_host_data(b"x")
    assert terminal.dirty is True
