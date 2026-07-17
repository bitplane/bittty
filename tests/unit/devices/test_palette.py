"""Palette: seeding, OSC overrides/queries, resolution, and construction overrides."""

from bittty.palette import XTERM_16, format_rgb, parse_color_spec
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


def _terminal(**kwargs):
    board = Board(width=80, height=24, **kwargs)
    transport = RecordingTransport()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_parse_color_spec_forms():
    assert parse_color_spec("rgb:ffff/0000/8080") == (255, 0, 128)
    assert parse_color_spec("rgb:ff/00/80") == (255, 0, 128)
    assert parse_color_spec("#ff0080") == (255, 0, 128)
    assert parse_color_spec("#f08") == (255, 0, 136)
    assert parse_color_spec("teal") is None  # named colours are not supported


def test_resolve_uses_the_palette():
    board, _, _ = _terminal()
    palette = board.palette
    assert palette.resolve(Color("indexed", 1)) == XTERM_16[1]  # red3
    assert palette.resolve(Color("rgb", (10, 20, 30))) == (10, 20, 30)
    assert palette.resolve(Color("default")) is None  # caller supplies the default


def test_osc4_sets_and_queries_a_palette_entry():
    board, parser, transport = _terminal()
    parser.feed("\x1b]4;1;rgb:1234/5678/9abc\x07")
    assert board.palette.resolve(Color("indexed", 1)) == (0x12, 0x56, 0x9A)

    parser.feed("\x1b]4;1;?\x07")
    assert transport.data == [f"\x1b]4;1;{format_rgb((0x12, 0x56, 0x9A))}\x07"]


def test_osc10_sets_foreground_then_reset_restores_it():
    board, parser, transport = _terminal()
    parser.feed("\x1b]10;#112233\x07")
    assert board.palette.foreground == (0x11, 0x22, 0x33)

    parser.feed("\x1b]110\x07")  # reset foreground to the model default
    assert board.palette.foreground == (255, 255, 255)


def test_construction_time_palette_overrides():
    board, _, _ = _terminal(palette_overrides={2: (1, 2, 3), "background": (9, 9, 9)})
    assert board.palette.resolve(Color("indexed", 2)) == (1, 2, 3)
    assert board.palette.background == (9, 9, 9)
