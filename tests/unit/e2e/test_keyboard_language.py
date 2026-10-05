"""The keyboard language: DSR (CSI ? 26 n), DECKBD, and what national mode makes the keyboard send.

VT220 and VT510 reference manuals (VT510 table 8-9): the keyboard language picks the national replacement set,
and in national mode (DECNRCM) the keyboard sends that set's 7-bit codes. xterm 407 answers
the DSR as a North American keyboard and ignores DECKBD (captured).
"""

import pytest

from bittty import Board, KeyEvent, MemoryConnection
from bittty.model import BITTTY, LINUX, VT220, VT510, XTERM


def _run(sequence, model=VT510):
    board = Board(width=40, height=4, model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(sequence.encode())
    return board, wire


@pytest.mark.parametrize(
    ("model", "sequence", "reply"),
    [
        (XTERM, "", "\x1b[?27;1;0;0n"),
        (XTERM, "\x1b[2;7 }", "\x1b[?27;1;0;0n"),  # DECKBD ignored
        (VT220, "", "\x1b[?27;1n"),  # the VT220 reports the language alone
        (VT510, "", "\x1b[?27;1;0;4n"),  # North American, ready, LK450
        (VT510, "\x1b[;7 }", "\x1b[?27;7;0;4n"),  # German
        (VT510, "\x1b[2;16 }", "\x1b[?27;16;0;5n"),  # Portuguese, enhanced PC (PCXAL)
        (VT510, "\x1b[1;0 }", "\x1b[?27;1;0;4n"),  # 0 is North American
        (VT510, "\x1b[;7 }\x1b[;17 }", "\x1b[?27;7;0;4n"),  # not a language: ignored
        (VT510, "\x1b[;7 }\x1b[3;2 }", "\x1b[?27;7;0;4n"),  # not a layout: ignored
        (VT510, "\x1b[;7 }\x1bc", "\x1b[?27;7;0;4n"),  # a Set-Up choice: RIS keeps it
        (BITTTY, "\x1b[;2 }", "\x1b[?27;2;0;4n"),
    ],
)
def test_keyboard_status_report(model, sequence, reply):
    _, wire = _run(sequence + "\x1b[?26n", model)
    assert wire.data == [reply]


def test_a_terminal_without_the_report_does_not_answer():
    _, wire = _run("\x1b[?26n", LINUX)
    assert wire.data == []


@pytest.mark.parametrize(
    ("language", "typed", "sent"),
    [
        (7, "Größe", "Gr|~e"),  # German
        (15, "Año ¿", "A|o ]"),  # Spanish
        (16, "ação", "a|{o"),  # Portuguese
        (5, "Øl", "\\l"),  # Danish
        (2, "£5", "#5"),  # British
        (28, "ç", "\\"),  # Canadian (English) uses French Canadian
        (1, "Größe", "Größe"),  # North American: ASCII, nothing to replace
        (8, "ĳ", "ĳ"),  # Dutch has no national set on the VT510
        (7, "é", "é"),  # a character the set lacks goes as it is
    ],
)
def test_national_mode_sends_the_keyboard_languages_set(language, typed, sent):
    board, wire = _run(f"\x1b[;{language} }}\x1b[?42h")
    board.input_text(typed)
    assert wire.text == sent


def test_multinational_mode_sends_characters_as_they_are():
    board, wire = _run("\x1b[;7 }")
    board.input_text("ä")
    assert wire.text == "ä"


def test_typed_keys_are_translated_too():
    board, wire = _run("\x1b[;7 }\x1b[?42h")
    board.input_key_event(KeyEvent("a", text="ä"))
    assert wire.text == "{"
