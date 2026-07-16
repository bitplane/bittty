"""Linux console fidelity: ESC ] P / ESC ] R palette, DECID, and its charset mappings."""

from bittty.parser import Parser
from bittty.personality import LINUX
from bittty.terminal import Terminal


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def _term(**kwargs):
    terminal = Terminal(width=20, height=3, **kwargs)
    return terminal, Parser(terminal.board)


def test_linux_set_palette_entry():
    terminal, parser = _term(personality=LINUX)
    parser.feed("\x1b]P4a0b0c0")  # set colour 4 to #a0b0c0 (no terminator)
    parser.feed("done")  # subsequent text must NOT be swallowed
    assert terminal.board.palette.colors[4] == (0xA0, 0xB0, 0xC0)
    assert terminal.board.screen.current_buffer.get_line_text(0).startswith("done")


def test_linux_set_palette_split_across_feeds():
    terminal, parser = _term(personality=LINUX)
    # Feed the sequence one byte at a time to exercise the wait-for-more path.
    for ch in "\x1b]P1ffffff":
        parser.feed(ch)
    parser.feed("X")
    assert terminal.board.palette.colors[1] == (255, 255, 255)
    assert terminal.board.screen.current_buffer.get_line_text(0).startswith("X")


def test_linux_reset_palette():
    terminal, parser = _term(personality=LINUX)
    parser.feed("\x1b]P200ff00")  # recolour entry 2
    assert terminal.board.palette.colors[2] == (0x00, 0xFF, 0x00)
    parser.feed("\x1b]R")  # reset the whole palette
    assert terminal.board.palette.colors[2] == (0, 170, 0)  # VGA green restored


def test_decid_answers_like_primary_da():
    terminal, parser = _term()
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    parser.feed("\x1bZ")  # DECID
    assert transport.data == ["\033[?62;1;6;8;9;15;18;21;22;23c"]  # xterm's DA1


def test_linux_recognises_the_ibm_pc_charset_designator():
    terminal, parser = _term(personality=LINUX)
    parser.feed("\x1b(U")  # designate G0 -> IBM PC ROM
    assert terminal.board.charset.g0_charset == "U"
