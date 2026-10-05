"""The VT102, VT320 and VT420 models, from their user guides' control-sequence references.

The VT102 added IL, DL, DCH, IRM and the printer port to the VT100; the VT220 added ICH and ECH.
The VT320 brought status lines, state reports and the user-preferred set; the VT420 margins,
rectangles, six pages of page memory, macros and the reports that carry pages.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import VT100, VT102, VT220, VT320, VT420, get_model


def _run(sequence, model):
    board = Board(width=20, height=24, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence.encode())
    return board, wire


def _line(board):
    return board.blitter.current_page.get_line_text(0).rstrip()


@pytest.mark.parametrize(
    ("model", "da1", "da2"),
    [
        (VT102, "\x1b[?6c", []),
        (VT320, "\x1b[?63;1;2;6;8;9c", ["\x1b[>24;10;0c"]),
        (VT420, "\x1b[?64;1;2;6;8;9;15;18;21c", ["\x1b[>41;10;0c"]),
    ],
)
def test_device_attributes(model, da1, da2):
    _, wire = _run("\x1b[c\x1b[>c", model)
    assert wire.data == [da1, *da2]


@pytest.mark.parametrize(("name", "model"), [("vt102", VT102), ("vt320", VT320), ("vt420", VT420)])
def test_term_names(name, model):
    assert get_model(name) is model


# --- the editing functions, by generation --- #

EDITING = {  # sequence: (as edited, as ignored)
    "\x1b[2P": ("cdef", "abcdef"),  # DCH
    "\x1b[2@": ("  abcdef", "abcdef"),  # ICH
    "\x1b[2X": ("  cdef", "abcdef"),  # ECH
    "\x1b[4hXY": ("XYabcdef", "XYcdef"),  # IRM
}


@pytest.mark.parametrize(
    ("model", "supported"),
    [(VT100, set()), (VT102, {"\x1b[2P", "\x1b[4hXY"}), (VT220, set(EDITING))],
)
@pytest.mark.parametrize("sequence", EDITING)
def test_editing_functions(model, supported, sequence):
    board, _ = _run("abcdef\x1b[H" + sequence, model)
    edited, ignored = EDITING[sequence]
    assert _line(board) == (edited if sequence in supported else ignored)


@pytest.mark.parametrize(("model", "supported"), [(VT100, False), (VT102, True)])
def test_line_editing(model, supported):
    board, _ = _run("one\r\ntwo\x1b[H\x1b[L", model)
    assert board.capture_text() == ("\none\ntwo" if supported else "one\ntwo")


def test_the_vt102_has_a_printer_port():
    _, wire = _run("\x1b[?15n", VT102)
    assert wire.data == ["\x1b[?13n"]


# --- VT320 --- #


def test_vt320_reports():
    _, wire = _run("\x1b[&u\x1b[?26n\x1b[?69$p\x1b[?66$p", VT320)
    assert wire.data == ["\x1bP0!u%5\x1b\\", "\x1b[?27;1n", "\x1b[?69;0$y", "\x1b[?66;2$y"]


def test_vt320_status_line_and_state_report():
    board, wire = _run("\x1b[2$~\x1b[1$}status\x1b[0$}\x1b[1$u", VT320)
    assert board.capture_status_line() == "status"
    assert wire.data[0].startswith("\x1bP1$s")


def test_vt320_has_one_page():
    board, _ = _run("", VT320)
    assert len(board.blitter.pages) == 1


# --- VT420 --- #


@pytest.mark.parametrize(("height", "pages"), [(24, 6), (25, 5), (36, 4), (48, 3), (72, 2), (30, 1)])
def test_vt420_page_memory(height, pages):
    board = Board(width=80, height=height, model=VT420)
    assert len(board.blitter.pages) == pages


def test_vt420_reports():
    _, wire = _run('\x1b[3U\x1b[2;3H\x1b[?6n\x1b["v\x1b[?26n\x1b[?62n\x1b[?69$p\x1b[?64$p', VT420)
    assert wire.data == [
        "\x1b[?2;3;4R",
        '\x1b[24;20;1;1;4"w',
        "\x1b[?27;1;0;1n",  # LK401
        "\x1b[0384*{",
        "\x1b[?69;2$y",
        "\x1b[?64;1$y",
    ]


def test_vt420_margins_and_rectangles():
    board, wire = _run("\x1b[?69h\x1b[3;5s\x1bP$qs\x1b\\\x1b[65;1;1;1;3$x", VT420)
    assert wire.data == ["\x1bP0$r3;5s\x1b\\"]
    assert _line(board) == "AAA"
