"""XTWINOPS, DECSCL, title stack, and shell-integration OSC (7, 9, 133, 777)."""

from bittty import Board, MemoryConnection
from bittty.parser import Parser


def _driver(width=80, height=24):
    board = Board(width=width, height=height)
    transport = MemoryConnection()
    board.host.attach(transport)
    return board, Parser(board), transport


def test_xtwinops_reports_size():
    _, parser, transport = _driver(80, 24)
    parser.feed("\x1b[18t")  # report text-area size in characters
    assert transport.data == ["\x1b[8;24;80t"]


def test_xtwinops_resizes():
    board, parser, _ = _driver(80, 24)
    parser.feed("\x1b[8;10;40t")  # resize to 10 rows, 40 cols
    assert (board.width, board.height) == (40, 10)


def test_xtwinops_title_stack():
    board, parser, _ = _driver()
    parser.feed("\x1b]2;first\x07")
    parser.feed("\x1b[22;0t")  # push
    parser.feed("\x1b]2;second\x07")
    assert board.title.title == "second"
    parser.feed("\x1b[23;0t")  # pop
    assert board.title.title == "first"


def test_decscl_records_conformance_level():
    board, parser, _ = _driver()
    parser.feed('\x1b[62"p')
    assert board.conformance_level == 62


def test_shell_integration_osc():
    board, parser, _ = _driver()
    parser.feed("\x1b]7;file:///home/gaz\x07")
    assert board.cwd == "file:///home/gaz"

    parser.feed("\x1b]9;build finished\x07")
    parser.feed("\x1b]777;notify;Title;Body\x07")
    assert board.notifications == ["build finished", "Title; Body"]

    parser.feed("\x1b[3;1H\x1b]133;A\x07")  # prompt mark at row 3 (0-based 2)
    assert board.prompt_marks == [("A", 2)]
