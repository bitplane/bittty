"""Correctness fixes: ESC % coding-system escapes, and RIS resetting the palette."""

from bittty.parser import Parser
from bittty.style import Color
from bittty import Board


def _term():
    terminal = Board(width=20, height=3)
    return terminal, Parser(terminal.board)


def test_esc_percent_is_consumed_not_leaked():
    terminal, parser = _term()
    parser.feed("\x1b%GHi")  # enable UTF-8, then "Hi"
    parser.feed("\x1b%@!")  # back to default, then "!"
    line = terminal.board.blitter.current_buffer.get_line_text(0)
    assert line.startswith("Hi!")  # no stray "G" or "@" leaked


def test_ris_resets_the_palette():
    terminal, parser = _term()
    parser.feed("\x1b]4;1;rgb:1234/5678/9abc\x07")  # override palette entry 1
    assert terminal.board.palette.resolve(Color("indexed", 1)) == (0x12, 0x56, 0x9A)

    parser.feed("\x1bc")  # RIS
    assert terminal.board.palette.resolve(Color("indexed", 1)) == (205, 0, 0)  # xterm red restored
