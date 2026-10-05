"""How xterm writes a paste to the host, captured from xterm 407 (pasting the PRIMARY selection).

Newlines go as carriage returns, unless readline newline pasting (2006) is set; readline
character-quoting (2005) sends each byte after a Ctrl-V (literal-next); and the controls of
disallowedPasteControls (BS, DEL, ENQ, EOT, ESC and NUL) are replaced by spaces.
"""

import pytest

from bittty import Board, MemoryConnection
from bittty.model import BITTTY, GNOME, XTERM

TEXT = "a\nb\r\nc\x01d\t"


def _paste(setup, text=TEXT, model=XTERM):
    board = Board(model=model)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(setup.encode())
    board.input_paste(text)
    return wire.text


@pytest.mark.parametrize(
    ("setup", "sent"),
    [
        ("", "a\rb\r\rc\x01d\t"),
        ("\x1b[?2006h", "a\nb\r\nc\x01d\t"),
        ("\x1b[?2005h", "\x16a\x16\r\x16b\x16\r\x16\r\x16c\x16\x01\x16d\x16\t"),
        ("\x1b[?2005h\x1b[?2006h", "\x16a\x16\n\x16b\x16\r\x16\n\x16c\x16\x01\x16d\x16\t"),
        ("\x1b[?2004h", "\x1b[200~a\rb\r\rc\x01d\t\x1b[201~"),
        ("\x1b[?2004h\x1b[?2005h", "\x1b[200~\x16a\x16\r\x16b\x16\r\x16\r\x16c\x16\x01\x16d\x16\t\x1b[201~"),
        ("\x1b[?2004h\x1b[?2006h", "\x1b[200~a\nb\r\nc\x01d\t\x1b[201~"),
    ],
)
def test_paste(setup, sent):
    assert _paste(setup) == sent


def test_disallowed_controls_become_spaces():
    assert _paste("", "x\x1by\x7fz\x08w\x00v\x04u\x05t") == "x y z w v u t"


def test_quoting_quotes_each_byte_of_a_character():
    """xterm quotes bytes, not characters."""
    assert _paste("\x1b[?2005h", "é") == "\x16\xc3\x16\xa9"


@pytest.mark.parametrize("mode", [2005, 2006])
def test_decrqm(mode):
    board = Board(model=XTERM)
    wire = MemoryConnection()
    board.host.attach(wire)
    board.feed_host_data(f"\x1b[?{mode}$p\x1b[?{mode}h\x1b[?{mode}$p".encode())
    assert wire.data == [f"\x1b[?{mode};2$y", f"\x1b[?{mode};1$y"]


@pytest.mark.parametrize("model", [BITTTY, GNOME])
def test_other_terminals_paste_as_it_comes(model):
    """bittty relays the outer terminal's paste, which that terminal has already prepared."""
    assert _paste("\x1b[?2005h", "a\nb\x1b", model) == "a\nb\x1b"
