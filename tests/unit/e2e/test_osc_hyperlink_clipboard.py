"""OSC 8 (hyperlinks) and OSC 52 (clipboard)."""

import base64

from bittty.parser import Parser
from bittty.style import Color
from bittty import Board


class RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def test_osc8_stamps_hyperlink_on_cells():
    terminal = Board(width=20, height=3)
    parser = Parser(terminal.board)
    parser.feed("\x1b]8;;http://example.com\x1b\\link")
    parser.feed("\x1b]8;;\x1b\\X")  # close the link, then a plain char

    buf = terminal.board.blitter.current_buffer
    assert buf.get_cell(0, 0)[0].hyperlink == "http://example.com"  # 'l'
    assert buf.get_cell(3, 0)[0].hyperlink == "http://example.com"  # 'k'
    assert buf.get_cell(4, 0)[0].hyperlink is None  # 'X'


def test_hyperlink_survives_sgr_reset_but_colour_does_not():
    terminal = Board(width=20, height=3)
    parser = Parser(terminal.board)
    parser.feed("\x1b]8;id=1;http://x\x1b\\")
    parser.feed("\x1b[31ma")  # red 'a' inside the link
    parser.feed("\x1b[0mb")  # SGR reset, then 'b'

    buf = terminal.board.blitter.current_buffer
    a, b = buf.get_cell(0, 0)[0], buf.get_cell(1, 0)[0]
    assert a.hyperlink == "http://x" and a.fg == Color("indexed", 1)
    assert b.hyperlink == "http://x"  # reset kept the link
    assert b.fg is None  # but cleared the colour


def test_osc52_set_and_query_clipboard():
    terminal = Board(width=20, height=3)
    transport = RecordingTransport()
    terminal.board.host.attach(transport)
    parser = Parser(terminal.board)

    encoded = base64.b64encode(b"hello").decode("ascii")
    parser.feed(f"\x1b]52;c;{encoded}\x07")
    assert terminal.board.clipboard["c"] == "hello"

    parser.feed("\x1b]52;c;?\x07")
    assert transport.data == [f"\x1b]52;c;{encoded}\x07"]
