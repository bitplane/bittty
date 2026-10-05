"""The host-writable status line: DECSSDT (CSI Ps $ ~) and DECSASD (CSI Ps $ }).

Behaviour from the VT510 reference manual (DECSSDT, DECSASD). The xterm 407
build used for the other fixtures has no status line, so none are captured.
"""

from dataclasses import replace

import pytest

from bittty import Board, MemoryConnection
from bittty.caps import TerminalCaps
from bittty.model import VT510, XTERM
from bittty.present import StatusLineChanged

WRITABLE = "\x1b[2$~\x1b[1$}"


class Recorder:
    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _run(sequence, model=VT510):
    board = Board(width=20, height=5, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    recorder = Recorder()
    board.display.attach(recorder)
    board.feed_host_data(sequence.encode())
    return board, wire, recorder.events


def _main(board):
    return [board.blitter.main_page.get_line_text(y).rstrip() for y in range(board.blitter.main_page.height)]


def test_text_goes_to_the_status_line_while_it_is_active():
    board, _, _ = _run("\x1b[3;4Hmain" + WRITABLE + "status\x1b[0$}!")
    assert board.capture_status_line() == "status"
    assert _main(board)[2] == "   main!"  # the main display's cursor was kept


def test_only_column_positions_operate_on_the_status_line():
    board, _, _ = _run(WRITABLE + "abc\x1b[4;10Hx\x1b[5Ay\x1b[3By\n\x1b[1Gz")
    assert board.capture_status_line() == "zbc      xyy"
    assert _main(board) == [""] * 5


def test_erasing_and_rendition_apply_on_the_status_line():
    board, _, _ = _run(WRITABLE + "abcdef\x1b[3G\x1b[K\x1b[1mX")
    assert board.capture_status_line() == "abX"
    assert board.blitter.status_page.get_cell(2, 0)[0].bold is True


@pytest.mark.parametrize("leave", ["\x1b[0$}", "\x1b[1$~", "\x1b[0$~", "\x1b[!p", '\x1b[64;1"p'])
def test_status_line_is_left_by(leave):
    """DECSASD 0, a status line type other than host-writable, DECSTR and DECSCL exit it."""
    board, _, _ = _run("\x1b[2;2H" + WRITABLE + "s" + leave + "m")
    assert not board.blitter.status_active
    assert _main(board)[1] == " m"


def test_ris_erases_and_exits_the_status_line():
    board, _, _ = _run(WRITABLE + "status\x1bc")
    assert not board.blitter.status_active
    assert board.capture_status_line() == ""
    assert board.blitter.status_type == 1  # back to the default indicator


def test_a_new_host_writable_status_line_is_empty():
    board, _, _ = _run(WRITABLE + "old\x1b[0$}\x1b[1$~\x1b[2$~")
    assert board.capture_status_line() == ""


def test_decsasd_needs_a_host_writable_status_line():
    board, _, _ = _run("\x1b[1$}text")
    assert not board.blitter.status_active
    assert _main(board)[0] == "text"


@pytest.mark.parametrize(
    ("sequence", "type_reply", "active_reply"),
    [("", "1$~", "0$}"), ("\x1b[2$~", "2$~", "0$}"), (WRITABLE, "2$~", "1$}"), ("\x1b[0$~", "0$~", "0$}")],
)
def test_decrqss_reports_the_status_line(sequence, type_reply, active_reply):
    board, wire, _ = _run(sequence + "\x1bP$q$~\x1b\\\x1bP$q$}\x1b\\")
    assert wire.data == [f"\x1bP0$r{type_reply}\x1b\\", f"\x1bP0$r{active_reply}\x1b\\"]


def test_the_chrome_hears_the_status_line_type():
    _, _, events = _run("\x1b[2$~\x1b[0$~\x1b[0$~")
    assert [e for e in events if isinstance(e, StatusLineChanged)] == [
        StatusLineChanged("host-writable"),
        StatusLineChanged("none"),
    ]


def test_a_terminal_without_a_status_line_ignores_it():
    board, wire, _ = _run(WRITABLE + "text\x1bP$q$~\x1b\\", model=XTERM)
    assert _main(board)[0] == "text"
    assert wire.data == ["\x1bP0$r$~\x1b\\"]


def test_page_size_reports_are_the_main_display_while_the_status_line_is_active():
    """The status line is one row, but the page is still 5 lines (DECSLPP, DECSNLS)."""
    board, wire, _ = _run(WRITABLE + "\x1bP$qt\x1b\\\x1bP$q*|\x1b\\")
    assert board.blitter.status_active
    assert wire.data == ["\x1bP0$r5t\x1b\\", "\x1bP0$r5*|\x1b\\"]


def test_the_status_line_measures_with_the_detected_ambiguous_width():
    board = Board(width=20, height=5, model=VT510)
    board.set_caps(replace(TerminalCaps.unknown(), ambiguous_width=2))
    board.feed_host_data((WRITABLE + "α|").encode())
    assert [board.blitter.status_page.get_cell(x, 0)[1] for x in range(3)] == ["α", "", "|"]
