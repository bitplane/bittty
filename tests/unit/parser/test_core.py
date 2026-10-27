"""Test core parser components."""

import pytest

from bittty.parser.core import Parser, parse_string_sequence


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
    """An ESC that is not ST abandons the OSC and begins the next sequence (xterm 407)."""
    parser.feed("Hello \x1b]2;some text here\x1b[A")
    parser.feed("more text\x07world")

    assert "Hello more textworld" in board.capture_pane()
    assert board.title.title != "some text here"


def test_parser_feed_multiple_escapes(parser, board):
    """Test that the parser handles multiple escape characters correctly."""
    parser.feed("hello\x1b\x1b")
    assert "hello" in board.capture_pane()
    # The second ESC begins the sequence again, so it waits for what follows
    assert parser.buffer == "\x1b"


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


@pytest.mark.parametrize("starter", ["\x1b]2;", "\x1bP", "\x1b_", "\x1b^", "\x1bX", "\x9d2;"])
@pytest.mark.parametrize("ending", ["\x1b\\", "\x9c", "\x07", "\x18", "\x1a", "\x1b[0m"])
def test_oversized_strings_are_discarded_until_terminated(board, starter, ending):
    parser = Parser(board, max_string_size=32)
    parser.feed(starter)
    for _ in range(10):
        parser.feed("x" * 16)
        assert len(parser.buffer) <= 36
    for char in ending:
        parser.feed(char)
    parser.feed("visible")
    assert board.capture_text() == "visible"
    assert board.title.title != "x" * 160
    assert parser.buffer == ""


def test_complete_oversized_string_is_not_dispatched(board):
    parser = Parser(board, max_string_size=32)
    parser.feed("\x1b]2;" + "x" * 40 + "\x07visible")
    assert board.title.title != "x" * 40
    assert board.capture_text() == "visible"


def test_string_scan_advances_and_keeps_split_terminator(parser, board):
    parser.feed("\x1b]2;hello")
    assert parser._scan_from == len(parser.buffer)
    parser.feed(" world\x1b")
    assert parser._scan_from == len(parser.buffer) - 1
    parser.feed("\\visible")
    assert board.title.title == "hello world"
    assert board.capture_text() == "visible"


def test_reset_leaves_oversized_string_discard_mode(board):
    parser = Parser(board, max_string_size=32)
    parser.feed("\x1b]2;" + "x" * 40)
    parser.reset()
    parser.feed("\x1b]2;new title\x07visible")
    assert board.title.title == "new title"
    assert board.capture_text() == "visible"


def test_flush_trailing_leaves_oversized_string_discard_mode(board):
    parser = Parser(board, max_string_size=8)
    parser.feed("\x1b]2;" + "x" * 20)
    parser.flush_trailing()
    parser.feed("visible")
    assert board.capture_text() == "visible"


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("title,accepted", [("abc", True), ("abcd", False)])
def test_string_size_limit_includes_delimiters(board, split, title, accepted):
    parser = Parser(board, max_string_size=9)
    sequence = "\x1b]2;" + title + "\x1b\\"
    chunks = sequence if split else [sequence]
    for chunk in chunks:
        parser.feed(chunk)
    assert (board.title.title == title) is accepted


@pytest.mark.parametrize("payload", ["R" * 40, "P0123456" * 10])
def test_discarded_osc_payload_cannot_become_linux_palette_command(board, payload):
    parser = Parser(board, max_string_size=8)
    operations = []
    parser.emit = operations.append
    parser.feed("\x1b]2;" + "x" * 20)
    parser.feed(payload + "\x07visible")
    assert not any(op.name.startswith("LINUX_PALETTE") for op in operations)
    assert board.capture_text() == "visible"
