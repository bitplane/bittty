"""OSC 8 (hyperlinks) and OSC 52 (clipboard)."""

import base64

from bittty import Board, MemoryConnection
from bittty.parser import Parser
from bittty.style import Color


def test_osc8_stamps_hyperlink_on_cells():
    board = Board(width=20, height=3)
    parser = Parser(board)
    parser.feed("\x1b]8;;http://example.com\x1b\\link")
    parser.feed("\x1b]8;;\x1b\\X")  # close the link, then a plain char

    buf = board.blitter.current_buffer
    assert buf.get_cell(0, 0)[0].hyperlink == "http://example.com"  # 'l'
    assert buf.get_cell(3, 0)[0].hyperlink == "http://example.com"  # 'k'
    assert buf.get_cell(4, 0)[0].hyperlink is None  # 'X'


def test_hyperlink_survives_sgr_reset_but_colour_does_not():
    board = Board(width=20, height=3)
    parser = Parser(board)
    parser.feed("\x1b]8;id=1;http://x\x1b\\")
    parser.feed("\x1b[31ma")  # red 'a' inside the link
    parser.feed("\x1b[0mb")  # SGR reset, then 'b'

    buf = board.blitter.current_buffer
    a, b = buf.get_cell(0, 0)[0], buf.get_cell(1, 0)[0]
    assert a.hyperlink == "http://x" and a.fg == Color("indexed", 1)
    assert b.hyperlink == "http://x"  # reset kept the link
    assert b.fg is None  # but cleared the colour


def test_osc52_set_and_query_clipboard():
    board = Board(width=20, height=3)
    transport = MemoryConnection()
    board.host.attach(transport)
    parser = Parser(board)

    encoded = base64.b64encode(b"hello").decode("ascii")
    parser.feed(f"\x1b]52;c;{encoded}\x07")
    assert board.clipboard["c"] == "hello"

    parser.feed("\x1b]52;c;?\x07")
    assert transport.data == [f"\x1b]52;c;{encoded}\x07"]


def test_osc8_id_param_is_kept():
    """OSC 8 ; id=chat ; uri ST — the id groups split segments of one link."""
    board = Board(width=30, height=3)
    board.parser.feed("\x1b]8;id=chat;https://example.com\x1b\\link text\x1b]8;;\x1b\\ plain")

    assert board.link_at(0, 0) == ("https://example.com", "chat")
    assert board.link_at(8, 0) == ("https://example.com", "chat")
    assert board.link_at(9, 0) is None  # after the close, no link

    extent = board.blitter.current_buffer.link_extent(4, 0)
    assert extent == ("https://example.com", "chat", 0, 8)


def test_osc8_without_id_and_run_boundaries():
    """Links without id= still work; adjacent different links are separate runs."""
    board = Board(width=40, height=2)
    board.parser.feed("\x1b]8;;http://a\x07aaa\x1b]8;;http://b\x07bbb\x1b]8;;\x07")

    assert board.link_at(1, 0) == ("http://a", None)
    assert board.blitter.current_buffer.link_extent(1, 0) == ("http://a", None, 0, 2)
    assert board.blitter.current_buffer.link_extent(4, 0) == ("http://b", None, 3, 5)
    assert board.blitter.current_buffer.link_extent(10, 0) is None


def test_osc8_id_distinguishes_touching_same_uri_links():
    """Two touching links to the same URI with different ids are two runs."""
    board = Board(width=40, height=2)
    board.parser.feed("\x1b]8;id=one;http://x\x07aa\x1b]8;id=two;http://x\x07bb\x1b]8;;\x07")

    assert board.blitter.current_buffer.link_extent(0, 0) == ("http://x", "one", 0, 1)
    assert board.blitter.current_buffer.link_extent(2, 0) == ("http://x", "two", 2, 3)
