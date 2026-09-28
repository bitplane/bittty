"""Supplemental sets: DEC Supplemental Graphic (%5), the user-preferred set (<), DECAUPSS and DECRQUPSS.

DEC Supplemental Graphic is the upper half of DEC's multinational set: GL code c shows c + 0x80,
save a few DEC glyphs and reserved positions (xterm's charsets.h, which shows reserved as ␦).
xterm maps GL-invoked supplemental sets only at those exceptions; the other positions keep the
byte, which a DEC terminal does not do, so bittty follows DEC there. Replies captured from xterm 407.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import LINUX, VT220, VT510, XTERM

GL = "".join(chr(c) for c in range(0x21, 0x7F))
SUPPLEMENTAL = "¡¢£␦¥␦§¤©ª«␦␦␦␦°±²³␦µ¶·␦¹º»¼½␦¿" "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏ␦ÑÒÓÔÕÖŒØÙÚÛÜŸ␦ß" "àáâãäåæçèéêëìíîï␦ñòóôõöœøùúûüÿ␦"


def _run(sequence, model=VT510, chunks=None):
    board = Board(width=100, height=4, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    for chunk in chunks or [sequence]:
        board.feed_host_data(chunk)
    return board, wire


def _text(board):
    return board.blitter.current_page.get_line_text(0).rstrip()


def test_dec_supplemental_graphic():
    board, _ = _run("\x1b(%5" + GL)
    assert _text(board) == SUPPLEMENTAL


@pytest.mark.parametrize(
    ("sequence", "text"),
    [
        ("\x1b)%5\x0e!(W}\x0fA", "¡¤ŒÿA"),  # through G1 and SO
        ("\x1b*%5\x1bN!x", "¡x"),  # through G2 and SS2
        ("\x1b(%5\x1b7\x1b(B\x1b8!", "¡"),  # DECSC keeps a two-character designation
    ],
)
def test_two_character_designators_parse(sequence, text):
    board, _ = _run(sequence)
    assert _text(board) == text


def test_a_designator_split_across_reads():
    board, _ = _run("", chunks=["\x1b(", "%", "5!"])
    assert _text(board) == "¡"


def test_deccir_reports_a_two_character_designation():
    """Captured from xterm 407."""
    _, wire = _run("\x1b)%5\x1b[1$w", XTERM)
    assert wire.data[0].endswith(";B%5BB\x1b\\")


def test_an_unknown_designation_is_consumed_and_ignored():
    """xterm 407 consumes ESC ( " ? (DEC Greek, which it lacks here) and prints nothing of it."""
    board, _ = _run('\x1b("?abc', XTERM)
    assert _text(board) == "abc"


# --- the user-preferred supplemental set --- #


@pytest.mark.parametrize("model", [VT510, VT220])
def test_the_user_preferred_set_is_dec_supplemental_by_default(model):
    board, _ = _run("\x1b(<" + GL, model)
    assert _text(board) == SUPPLEMENTAL


def test_xterm_prefers_ascii():
    """xterm in UTF-8 has no user-preferred set: it reports and shows ASCII (charproc.c)."""
    board, wire = _run("\x1b(<" + GL + "\x1b[&u", XTERM)
    assert _text(board) == GL
    assert wire.data == ["\x1bP0!uB\x1b\\"]


@pytest.mark.parametrize("assignment", ["\x1bP0!u%5\x1b\\", "\x1bP1!uA\x1b\\"])
def test_xterm_ignores_decaupss(assignment):
    """Captured from xterm 407."""
    _, wire = _run(assignment + "\x1b[&u", XTERM)
    assert wire.data == ["\x1bP0!uB\x1b\\"]


@pytest.mark.parametrize(
    ("assignment", "reply"),
    [
        ("", "\x1bP0!u%5\x1b\\"),
        ("\x1bP0!u%5\x1b\\", "\x1bP0!u%5\x1b\\"),
        ("\x1bP0!uB\x1b\\", "\x1bP0!u%5\x1b\\"),  # ASCII is not a supplemental set
        ("\x1bP1!u%5\x1b\\", "\x1bP0!u%5\x1b\\"),  # nor is %5 a 96-character set
        ("\x1bP0!u%5\x1b\\\x1bc", "\x1bP0!u%5\x1b\\"),
    ],
)
def test_decaupss_and_decrqupss(assignment, reply):
    _, wire = _run(assignment + "\x1b[&u")
    assert wire.data == [reply]


@pytest.mark.parametrize("model", [LINUX, VT220])
def test_a_terminal_without_a_user_preference_does_not_report_one(model):
    _, wire = _run("\x1b[&u", model)
    assert wire.data == []
