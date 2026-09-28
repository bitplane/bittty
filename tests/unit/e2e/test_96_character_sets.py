"""96-character sets: ESC - F, ESC . F and ESC / F designate G1-G3 (ISO 2022; there is no G0 form).

A 96-character set fills all of 2/0-7/15 (or 10/0-15/15 in GR), so it replaces the space too.
The ISO sets are the upper halves of ISO 8859: GR byte b shows the codepage's b, and GL code c
shows c + 0x80. xterm in UTF-8 leaves GL-invoked ISO sets alone, which no ISO 2022 terminal
does, so bittty follows the standard there. DECCIR replies captured from xterm 407.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import LINUX, VT220, VT510, XTERM


def _run(sequence, model=VT510):
    board = Board(width=40, height=3, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence)
    return board, wire


def _text(board):
    return board.blitter.current_page.get_line_text(0)


def _upper(codec):
    """The upper half of an ISO 8859 codepage as a 96-character set: each position's character."""
    return "".join(bytes([code]).decode(codec, errors="replace") for code in range(0xA0, 0x100))


@pytest.mark.parametrize(
    ("designator", "codec"),
    [
        ("A", "latin_1"),
        ("B", "iso8859_2"),
        ("F", "iso8859_7"),
        ("H", "iso8859_8"),
        ("L", "iso8859_5"),
        ("M", "iso8859_9"),
    ],
)
def test_gr_through_an_iso_set(designator, codec):
    gr = "".join(chr(code) for code in range(0xA0, 0x100))
    board, _ = _run(f"\x1b.{designator}\x1b}}" + gr[:40])  # G2 into GR
    expected = _upper(codec)[:40].replace("�", "␦")  # an unassigned position is reserved
    assert _text(board) == expected


def test_gl_through_a_96_character_set_includes_space():
    board, _ = _run("\x1b-A\x0e a!\x0fb")
    assert _text(board).rstrip() == "\xa0á¡b"


def test_single_shift_into_a_96_character_set():
    board, _ = _run("\x1b/B\x1bOa")  # G3 = Latin-2, SS3
    assert _text(board).rstrip() == "á"


@pytest.mark.parametrize(
    ("sequence", "tail"),
    [
        ("\x1b-A", ";0;2;B;BABB\x1b\\"),  # Scss: G1 holds a 96-character set
        ("\x1b.A\x1b/B", ";0;2;D;BBAB\x1b\\"),  # Latin-2 is a VT5xx set, beyond xterm's level
        ("\x1b-A\x1b)0", ";0;2;@;B0BB\x1b\\"),  # a 94-character designation replaces it
    ],
)
def test_deccir_reports_96_character_sets(sequence, tail):
    """Captured from xterm 407."""
    _, wire = _run(sequence + "\x1b[1$w", XTERM)
    assert wire.data[0].endswith(tail)


def test_xterm_knows_latin_1_alone_of_the_iso_sets():
    """xterm 407 at its VT4xx level ignores the VT5xx sets (charproc.c scs_table)."""
    board, _ = _run("\x1b-B\x1b.F\x1b/L\x1b)H\x1b)M", XTERM)
    assert board.charset.charset_array == ["B", "B", "B", "B"]


def test_decrsps_restores_96_character_sets():
    board, _ = _run("\x1bP1$t1;1;1;@;@;@;0;2;D;BBAB\x1b\\")
    assert board.charset.charset_array == ["B", "B", "96A", "B"]


def test_decsc_saves_96_character_sets():
    board, _ = _run("\x1b-A\x1b7\x1b)B\x1b8\x0ea")
    assert _text(board).rstrip() == "á"


@pytest.mark.parametrize(
    ("assignment", "text", "reply"),
    [
        ("\x1bP1!uA\x1b\\", "¡", "\x1bP1!uA\x1b\\"),
        ("\x1bP1!uB\x1b\\", "Ą", "\x1bP1!uB\x1b\\"),
        ("\x1bP0!uA\x1b\\", "¡", "\x1bP0!u%5\x1b\\"),  # A is not a 94-character supplemental set
    ],
)
def test_decaupss_assigns_96_character_sets(assignment, text, reply):
    board, wire = _run(assignment + "\x1b(<!\x1b[&u")
    assert _text(board).rstrip() == text
    assert wire.data == [reply]


@pytest.mark.parametrize("model", [VT220, LINUX])
def test_terminals_without_96_character_sets_ignore_them(model):
    board, _ = _run("\x1b-A\x0ea", model)
    assert _text(board).rstrip() == "a"
