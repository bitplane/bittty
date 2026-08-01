"""Linux console fidelity: ESC ] P / ESC ] R palette, DECID, and its charset mappings."""

from bittty import Board, MemoryConnection
from bittty.model import LINUX
from bittty.parser import Parser


def _term(**kwargs):
    board = Board(width=20, height=3, **kwargs)
    return board, Parser(board)


def test_linux_set_palette_entry():
    board, parser = _term(model=LINUX)
    parser.feed("\x1b]P4a0b0c0")  # set colour 4 to #a0b0c0 (no terminator)
    parser.feed("done")  # subsequent text must NOT be swallowed
    assert board.palette.colors[4] == (0xA0, 0xB0, 0xC0)
    assert board.blitter.current_buffer.get_line_text(0).startswith("done")


def test_linux_set_palette_split_across_feeds():
    board, parser = _term(model=LINUX)
    # Feed the sequence one byte at a time to exercise the wait-for-more path.
    for ch in "\x1b]P1ffffff":
        parser.feed(ch)
    parser.feed("X")
    assert board.palette.colors[1] == (255, 255, 255)
    assert board.blitter.current_buffer.get_line_text(0).startswith("X")


def test_linux_reset_palette():
    board, parser = _term(model=LINUX)
    parser.feed("\x1b]P200ff00")  # recolour entry 2
    assert board.palette.colors[2] == (0x00, 0xFF, 0x00)
    parser.feed("\x1b]R")  # reset the whole palette
    assert board.palette.colors[2] == (0, 170, 0)  # VGA green restored


def test_decid_answers_like_primary_da():
    board, parser = _term()
    transport = MemoryConnection()
    board.host.attach(transport)
    parser.feed("\x1bZ")  # DECID
    assert transport.data == ["\033[?62;1;2;6;8;9;15;18;21;22;23c"]  # bittty's DA1


def test_linux_recognises_the_ibm_pc_charset_designator():
    board, parser = _term(model=LINUX)
    parser.feed("\x1b(U")  # designate G0 -> IBM PC ROM
    assert board.charset.g0_charset == "U"
