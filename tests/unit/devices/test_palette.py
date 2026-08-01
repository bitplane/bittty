"""Palette: seeding, OSC overrides/queries, resolution, and construction overrides."""

from bittty import Board, MemoryConnection
from bittty.palette import XTERM_16, format_rgb, parse_color_spec
from bittty.parser import Parser
from bittty.style import Color


def _terminal(**kwargs):
    board = Board(width=80, height=24, **kwargs)
    transport = MemoryConnection()
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


def test_generation_bumps_on_colour_changes():
    board, parser, _ = _terminal()
    palette = board.palette

    seen = palette.generation
    parser.feed("\x1b]4;1;#ff0000\x07")  # OSC 4: palette entry
    assert palette.generation > seen

    seen = palette.generation
    parser.feed("\x1b]11;#101010\x07")  # OSC 11: default background
    assert palette.generation > seen

    seen = palette.generation
    parser.feed("\x1b[#P\x1b[#Q")  # XTPUSHCOLORS / XTPOPCOLORS
    assert palette.generation > seen

    seen = palette.generation
    palette.reset()
    assert palette.generation > seen


def test_generation_is_stable_without_colour_operations():
    board, parser, _ = _terminal()
    seen = board.palette.generation
    parser.feed("plain text\x1b[31mred\x1b[0m")  # SGR is not a palette op
    assert board.palette.generation == seen
