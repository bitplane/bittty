"""DA3, DECSCA + DECSED/DECSEL (selective erase), and DECUDK."""

from bittty.parser import Parser
from bittty.personality import VT100
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _driver(**kwargs):
    terminal = Board(width=20, height=5, **kwargs)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    return terminal, Parser(terminal.board), transport


def test_da3_answers_on_xterm_and_is_silent_on_vt100():
    _, parser, transport = _driver()
    parser.feed("\x1b[=c")  # tertiary DA
    assert transport.data == ["\x1bP!|00000000\x1b\\"]

    _, parser, transport = _driver(personality=VT100)
    parser.feed("\x1b[=c")
    assert transport.data == []  # a VT100 predates DA3


def test_selective_erase_keeps_protected_characters():
    terminal, parser, _ = _driver()
    parser.feed('\x1b[1"q')  # DECSCA: protect
    parser.feed("KEEP")
    parser.feed('\x1b[0"q')  # DECSCA: unprotect
    parser.feed("gone")
    parser.feed("\x1b[1;1H")  # home
    parser.feed("\x1b[?2J")  # DECSED: selective erase all

    line = terminal.board.screen.current_buffer.get_line_text(0)
    assert line.startswith("KEEP")  # protected text survives
    assert "gone" not in line  # unprotected text erased


def test_decudk_redefines_a_function_key():
    terminal, parser, transport = _driver()
    # DECUDK: define key 17 (F6) to send "HELLO"; St is the hex of the string.
    hexstr = "HELLO".encode("latin-1").hex().upper()
    parser.feed(f"\x1bP0;0|17/{hexstr}\x1b\\")
    assert terminal.board.keyboard.user_defined_keys[6] == "HELLO"

    terminal.input_fkey(6)  # F6 now sends the user string, not the keymap default
    assert transport.data == ["HELLO"]
