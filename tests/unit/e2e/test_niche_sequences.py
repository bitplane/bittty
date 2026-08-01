"""DA3, DECSCA + DECSED/DECSEL (selective erase), and DECUDK."""

from bittty import Board, MemoryConnection
from bittty.model import VT100
from bittty.parser import Parser


def _driver(**kwargs):
    board = Board(width=20, height=5, **kwargs)
    transport = MemoryConnection()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_da3_answers_on_xterm_and_is_silent_on_vt100():
    _, parser, transport = _driver()
    parser.feed("\x1b[=c")  # tertiary DA
    assert transport.data == ["\x1bP!|00000000\x1b\\"]

    _, parser, transport = _driver(model=VT100)
    parser.feed("\x1b[=c")
    assert transport.data == []  # a VT100 predates DA3


def test_selective_erase_keeps_protected_characters():
    board, parser, _ = _driver()
    parser.feed('\x1b[1"q')  # DECSCA: protect
    parser.feed("KEEP")
    parser.feed('\x1b[0"q')  # DECSCA: unprotect
    parser.feed("gone")
    parser.feed("\x1b[1;1H")  # home
    parser.feed("\x1b[?2J")  # DECSED: selective erase all

    line = board.blitter.current_buffer.get_line_text(0)
    assert line.startswith("KEEP")  # protected text survives
    assert "gone" not in line  # unprotected text erased


def test_decudk_redefines_a_function_key():
    board, parser, transport = _driver()
    # DECUDK: define key 17 (F6) to send "HELLO"; St is the hex of the string.
    hexstr = "HELLO".encode("latin-1").hex().upper()
    parser.feed(f"\x1bP0;0|17/{hexstr}\x1b\\")
    assert board.keyboard.user_defined_keys[6] == "HELLO"

    board.input_fkey(6)  # F6 now sends the user string, not the keymap default
    assert transport.data == ["HELLO"]
