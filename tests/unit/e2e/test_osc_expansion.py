"""OSC expansion: pointer shape (22), font (50), dynamic colours (13/14/17/19),
their resets (113/114/117/119), and Kitty notifications (99)."""

from bittty import Board, MemoryConnection
from bittty.parser import Parser
from bittty.present import Notification


class _Recorder:
    def __init__(self):
        self.events = []

    def present(self, event):
        self.events.append(event)


def _term():
    board = Board(width=20, height=3)
    transport = MemoryConnection()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_osc_22_sets_the_pointer_shape():
    board, parser, _ = _term()
    parser.feed("\x1b]22;pointer\x07")
    assert board.pointer_shape == "pointer"


def test_osc_50_sets_and_queries_the_font():
    board, parser, transport = _term()
    parser.feed("\x1b]50;Fira Code 12\x07")
    assert board.font == "Fira Code 12"
    parser.feed("\x1b]50;?\x07")
    assert transport.data[-1] == "\x1b]50;Fira Code 12\x07"


def test_dynamic_colour_set_and_query_roundtrip():
    board, parser, transport = _term()
    parser.feed("\x1b]13;rgb:ffff/0000/0000\x07")  # mouse foreground = red
    parser.feed("\x1b]13;?\x07")
    assert transport.data[-1] == "\x1b]13;rgb:ffff/0000/0000\x07"


def test_unset_dynamic_colour_query_falls_back_to_text_colour():
    board, parser, transport = _term()
    parser.feed("\x1b]10;?\x07")  # text foreground
    fg = transport.data[-1]
    parser.feed("\x1b]13;?\x07")  # mouse foreground, unset -> mirrors text fg
    mouse_fg = transport.data[-1]
    # same colour value, different OSC number
    assert fg.split(";", 1)[1] == mouse_fg.split(";", 1)[1]


def test_dynamic_colour_reset():
    board, parser, transport = _term()
    parser.feed("\x1b]17;rgb:1010/2020/3030\x07")  # highlight background
    assert board.palette.highlight_background is not None
    parser.feed("\x1b]117;\x07")  # reset it
    assert board.palette.highlight_background is None


def test_osc_99_is_a_desktop_notification():
    board, parser, _ = _term()
    recorder = _Recorder()
    board.display.attach(recorder)
    parser.feed("\x1b]99;i=1:d=0;Build finished\x07")  # kitty: metadata ; payload
    assert Notification("Build finished") in recorder.events
