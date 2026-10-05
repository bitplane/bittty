"""xterm's chrome resources as modes: the board keeps them, answers DECRQM, and tells the chrome,
which does the work (a scrollbar, scrolling to the bottom, selections and the clipboard).

Defaults captured from xterm 407, as are its read-only resources (13, and 1020-1023: utf8,
cjkWidth, emojiWidth and privateWidth), which the host can query but not set.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import BITTTY, VT510, XTERM
from bittty.present import ChromeResourcesChanged

RESOURCES = {  # mode: (name, xterm 407's default)
    30: ("scrollbar", False),
    35: ("font-shifting", True),
    1010: ("scroll-on-output", True),
    1011: ("scroll-on-key", False),
    1014: ("fast-scroll", True),
    1040: ("keep-selection", True),
    1041: ("select-to-clipboard", False),
    1044: ("keep-clipboard", False),
}


class Recorder:
    def __init__(self):
        self.events = []

    keeps_scrollback = False

    def present(self, event):
        self.events.append(event)


def _run(sequence, model=XTERM):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    recorder = Recorder()
    board.display.attach(recorder)
    board.feed_host_data(sequence.encode())
    return wire.data, [event.enabled for event in recorder.events if isinstance(event, ChromeResourcesChanged)]


DEFAULTS = frozenset(name for name, on in RESOURCES.values() if on)


@pytest.mark.parametrize(("mode", "resource"), RESOURCES.items())
def test_defaults_and_changes(mode, resource):
    name, default = resource
    toggle = "l" if default else "h"
    replies, events = _run(f"\x1b[?{mode}$p\x1b[?{mode}{toggle}\x1b[?{mode}$p")
    assert replies == [f"\x1b[?{mode};{2 - default}$y", f"\x1b[?{mode};{1 + default}$y"]
    assert events == [DEFAULTS ^ {name}]


def test_an_unchanged_resource_tells_the_chrome_nothing():
    _, events = _run("\x1b[?35h\x1b[?30l")
    assert events == []


def test_ris_restores_the_defaults():
    _, events = _run("\x1b[?30h\x1bc")
    assert events == [DEFAULTS | {"scrollbar"}, DEFAULTS]


@pytest.mark.parametrize(("mode", "status"), [(13, 2), (1020, 1), (1021, 2), (1022, 2), (1023, 1)])
def test_read_only_resources(mode, status):
    replies, _ = _run(f"\x1b[?{mode}h\x1b[?{mode}l\x1b[?{mode}$p")
    assert replies == [f"\x1b[?{mode};{status}$y"]


def test_bittty_has_them_too():
    replies, _ = _run("\x1b[?30$p\x1b[?1020$p", BITTTY)
    assert replies == ["\x1b[?30;2$y", "\x1b[?1020;1$y"]


def test_a_dec_terminal_has_no_chrome_resources():
    replies, _ = _run("\x1b[?30$p\x1b[?1020$p", VT510)
    assert replies == ["\x1b[?30;0$y", "\x1b[?1020;0$y"]
