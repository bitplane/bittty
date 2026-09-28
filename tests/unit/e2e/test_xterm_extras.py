"""xterm extras: title modes (XTSMTITLE/XTRMTITLE), pointer mode (XTSMPOINTER) and XTREPORTSGR.

Replies captured from xterm 407.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import LINUX, XTERM
from bittty.present import PointerModeChanged


class Recorder:
    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _run(sequence, model=XTERM):
    board = Board(width=80, height=24, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    recorder = Recorder()
    board.display.attach(recorder)
    board.feed_host_data(sequence)
    return board, wire, recorder.events


# --- title modes --- #


@pytest.mark.parametrize(
    ("sequence", "reply"),
    [
        ("\x1b]2;héllo\x1b\\\x1b[21t", "\x1b]lhéllo\x1b\\"),
        ("\x1b[>1t\x1b]2;héllo\x1b\\\x1b[21t", "\x1b]l68C3A96C6C6F\x1b\\"),  # query in hex: the UTF-8 bytes
        ("\x1b[>1t\x1b]1;python\x1b\\\x1b[20t", "\x1b]L707974686F6E\x1b\\"),
        ("\x1b[>0t\x1b]2;414243\x1b\\\x1b[21t", "\x1b]lABC\x1b\\"),  # set in hex
        ("\x1b[>0t\x1b]2;414243\x1b\\\x1b]2;4142zz\x1b\\\x1b[21t", "\x1b]lABC\x1b\\"),  # bad hex: unchanged
        ("\x1b[>0;1t\x1b[>0;1T\x1b]2;414243\x1b\\\x1b[21t", "\x1b]l414243\x1b\\"),  # reset
        ("\x1b[>1t\x1b[>T\x1b]2;AB\x1b\\\x1b[21t", "\x1b]l4142\x1b\\"),  # a bare reset resets nothing
        ("\x1b[>1t\x1b[!p\x1b]2;AB\x1b\\\x1b[21t", "\x1b]l4142\x1b\\"),  # DECSTR keeps them
        ("\x1b[>1t\x1bc\x1b]2;AB\x1b\\\x1b[21t", "\x1b]lAB\x1b\\"),  # RIS does not
        ("\x1b[>3t\x1b]2;héllo\x1b\\\x1b[21t", "\x1b]lhéllo\x1b\\"),  # the UTF-8 modes change nothing here
    ],
)
def test_title_modes(sequence, reply):
    _, wire, _ = _run(sequence)
    assert wire.data == [reply]


@pytest.mark.parametrize(
    ("setup", "report"),
    [
        ("", ">0;0;0;0t"),
        ("\x1b[>1t", ">0;1;0;0t"),
        ("\x1b[>0;3t", ">1;0;0;1t"),
        ("\x1b[>0;1;2;3t\x1b[>1T", ">1;0;1;1t"),
        ("\x1b[>0;1;2;3t\x1b[>1T\x1b[>T\x1b[>9t", ">1;0;1;1t"),
    ],
)
def test_decrqss_reports_the_title_modes(setup, report):
    _, wire, _ = _run(setup + "\x1bP$q>t\x1b\\")
    assert wire.data == [f"\x1bP1$r{report}\x1b\\"]


# --- pointer mode --- #


def test_pointer_mode_goes_to_the_chrome():
    _, _, events = _run("\x1b[>2p\x1b[>p\x1b[>9p\x1b[>0p")
    assert [e.mode for e in events if isinstance(e, PointerModeChanged)] == [2, 1, 0]


# --- XTREPORTSGR --- #

CELLS = "\x1b[H\x1b[1;31mAB\x1b[0;4mC\x1b[1mD\x1b[0m"


@pytest.mark.parametrize(
    ("rectangle", "reply"),
    [
        ("1;1;1;2", "0;1;31"),  # xterm reports bold red as 91 (its boldColors)
        ("1;1;1;3", "0"),
        ("1;3;1;4", "0;4"),
        ("1;4;1;4", "0;1;4"),
        ("1;5;1;5", "0"),
        ("5;5;1;1", "0"),
    ],
)
def test_xtreportsgr_reports_what_the_cells_share(rectangle, reply):
    _, wire, _ = _run(CELLS + f"\x1b[{rectangle}#|")
    assert wire.data == [f"\x1b[{reply}m"]


def test_xtreportsgr_reports_colours_in_their_colon_forms():
    _, wire, _ = _run("\x1b[2;1H\x1b[38;5;100;48;2;1;2;3;7mE\x1b[0m\x1b[2;1;2;1#|")
    assert wire.data == ["\x1b[0;7;38:5:100;48:2::1:2:3m"]


def test_a_terminal_without_the_extras_ignores_them():
    _, wire, events = _run("\x1b[>1t\x1b]2;AB\x1b\\\x1b[>2p\x1b[1;1;1;1#|", LINUX)
    assert wire.data == [] and not [e for e in events if isinstance(e, PointerModeChanged)]
