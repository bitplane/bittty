"""Test core parser components."""

import pytest

from bittty.parser.core import parse_string_sequence


@pytest.mark.parametrize(
    "sequence_type, data, expected",
    [
        # DCS sequences
        ("dcs", b"\x1bP0;1;2$p\x1b\\", "0;1;2$p"),
        ("dcs", b"\x1bP...\x07", "..."),
        ("dcs", b"\x1bPnoterm", "noterm"),
        # APC sequences
        ("apc", b"\x1b_some_command\x1b\\", "some_command"),
        ("apc", b"\x1b_noterm", "noterm"),
        # PM sequences
        ("pm", b"\x1b^a_message\x1b\\", "a_message"),
        ("pm", b"\x1b^noterm", "noterm"),
        # SOS sequences
        ("sos", b"\x1bXstart_of_string\x1b\\", "start_of_string"),
        ("sos", b"\x1bXnoterm", "noterm"),
        # OSC sequences with different terminators
        ("osc", b"\x1b]2;new title\x07", "2;new title"),
        ("osc", b"\x1b]2;new title\x1b\\", "2;new title"),
        ("osc", b"\x1b]2;no_terminator", "2;no_terminator"),
        # Edge cases
        ("osc", b"\x1b]", ""),  # Empty sequence
        ("unknown", b"\x1b]2;new title\x07", ""),  # Unknown type
        ("osc", b"invalid", ""),  # Invalid prefix
    ],
)
def test_parse_string_sequence(sequence_type, data, expected):
    """Test the string sequence parser with various sequence types and terminators."""
    assert parse_string_sequence(data.decode("latin-1"), sequence_type) == expected


def test_parser_feed_interrupted_osc(parser, board):
    """Test that the parser handles an OSC sequence interrupted by another escape."""
    # OSC sequence containing an escape, split across two feeds
    parser.feed("Hello \x1b]2;some text here\x1b[A")
    parser.feed("more text\x07world")

    assert "Hello world" in board.capture_pane()
    assert board.title.title == "some text here\x1b[Amore text"


def test_parser_feed_multiple_escapes(parser, board):
    """Test that the parser handles multiple escape characters correctly."""
    parser.feed("hello\x1b\x1b")
    assert "hello" in board.capture_pane()
    # The two escape characters should be consumed and dispatched as 'esc' events
    assert parser.buffer == ""


def test_parser_feed_simple_truncate(parser, board):
    """Test a simple truncated escape sequence."""
    parser.feed("hello\x1b")
    assert "hello" in board.capture_pane()
    assert parser.buffer == "\x1b"

    parser.feed("[1;1H")
    assert board.cursor.x == 0
    assert board.cursor.y == 0
    assert parser.buffer == ""


def test_charset_designation_split_across_chunks():
    """ESC ( arriving at the end of a chunk must wait for its designator."""
    from bittty import Board

    board = Board(width=20, height=5)
    board.parser.feed("\x1b(")
    board.parser.feed("0")
    board.parser.feed("q")  # DEC special graphics: q is '─'
    assert board.charset.g0_charset == "0"
    assert board.blitter.current_page.get_line_text(0)[0] == "─"


def test_decaln_split_across_chunks():
    """ESC # arriving at the end of a chunk must wait for its final byte."""
    from bittty import Board

    board = Board(width=4, height=2)
    board.parser.feed("\x1b#")
    board.parser.feed("8")
    assert board.blitter.current_page.get_line_text(0) == "EEEE"


def test_flush_trailing_releases_held_bytes():
    """Input-direction escape hatch: a dangling prefix comes out as plain text."""

    class Recorder:
        def __init__(self):
            self.ops = []

        def handle_operation(self, op):
            self.ops.append(op)

    from bittty.parser import Parser

    parser = Parser(Recorder())
    parser.feed("\x1b")  # lone ESC: held as a possible sequence prefix
    assert parser.sink.ops == []

    parser.flush_trailing()
    assert [(op.name, op.raw) for op in parser.sink.ops] == [("PRINT", "\x1b")]

    parser.flush_trailing()  # idempotent when nothing is held
    assert len(parser.sink.ops) == 1

    parser.feed("\x1b[<0;3;")  # incomplete CSI: held mid-sequence
    parser.flush_trailing()
    assert parser.sink.ops[-1].raw == "\x1b[<0;3;"
    parser.feed("hello")  # parser is back in ground and healthy
    assert parser.sink.ops[-1].raw == "hello"
