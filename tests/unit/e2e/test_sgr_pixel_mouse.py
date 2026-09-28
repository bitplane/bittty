"""SGR-Pixels mouse mode (1016): SGR reports whose coordinates are the pointer's pixels, one-based
from the text area's top-left (xterm button.c). A chrome that knows the pixel passes it; else the
board reports the cell's top-left pixel from the cell size the chrome reported."""

import pytest

from bittty import Board, MemoryConnection
from bittty.caps import TerminalCaps
from bittty.model import VT510, XTERM


def _mouse(setup, *args, model=XTERM, cell_px=None, **kwargs):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    if cell_px:
        board.set_caps(TerminalCaps(cell_px=cell_px))
    board.feed_host_data(setup)
    board.input_mouse(*args, **kwargs)
    return wire.text


@pytest.mark.parametrize(
    ("event_type", "sent"),
    [("press", "\x1b[<0;101;41M"), ("release", "\x1b[<0;101;41m")],
)
def test_pixel_reports(event_type, sent):
    assert _mouse("\x1b[?1000;1016h", 3, 2, 0, event_type, set(), pixel=(100, 40)) == sent


def test_without_a_pixel_the_cell_corner_is_reported():
    assert _mouse("\x1b[?1000;1016h", 3, 2, 0, "press", set(), cell_px=(8, 16)) == "\x1b[<0;17;17M"


def test_sgr_cells_are_unchanged():
    assert _mouse("\x1b[?1000;1006h", 3, 2, 0, "press", set(), pixel=(100, 40)) == "\x1b[<0;3;2M"


def test_pixel_mode_replaces_sgr_mode():
    board = Board(model=XTERM)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data("\x1b[?1006h\x1b[?1016h\x1b[?1006$p\x1b[?1016$p")
    assert wire.data == ["\x1b[?1006;2$y", "\x1b[?1016;1$y"]


def test_a_terminal_without_it():
    assert _mouse("\x1b[?1000;1016h", 3, 2, 0, "press", set(), model=VT510, pixel=(100, 40)) == ""
