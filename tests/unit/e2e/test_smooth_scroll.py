"""DECSCLM (mode 4): smooth scroll, "at a maximum rate of six lines per second" (VT100 user guide).
Scrolling is the chrome's to animate; the board keeps the mode and tells it through on_smooth_scroll.
The VT320, VT420 and VT510 power on smooth; xterm 407 jumps (captured)."""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import LINUX, VT100, VT320, VT420, VT510, XTERM
from bittty.present import SmoothScrollChanged


class Recorder:
    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _run(sequence, model):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    recorder = Recorder()
    board.display.attach(recorder)
    board.feed_host_data(sequence.encode())
    return wire.data, [e.enabled for e in recorder.events if isinstance(e, SmoothScrollChanged)]


@pytest.mark.parametrize(("model", "status"), [(XTERM, 2), (VT100, 2), (VT320, 1), (VT420, 1), (VT510, 1)])
def test_power_on(model, status):
    assert _run("\x1b[?4$p", model)[0] == [f"\x1b[?4;{status}$y"]


def test_the_chrome_hears_each_change():
    replies, events = _run("\x1b[?4h\x1b[?4h\x1b[?4$p\x1b[?4l", XTERM)
    assert replies == ["\x1b[?4;1$y"] and events == [True, False]


def test_decstr_keeps_it_and_ris_restores_it():
    replies, _ = _run("\x1b[?4h\x1b[!p\x1b[?4$p\x1bc\x1b[?4$p", XTERM)
    assert replies == ["\x1b[?4;1$y", "\x1b[?4;2$y"]


def test_the_linux_console_has_no_smooth_scroll():
    assert _run("\x1b[?4$p", LINUX)[0] == ["\x1b[?4;0$y"]
