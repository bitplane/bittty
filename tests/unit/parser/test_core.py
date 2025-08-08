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


def test_parser_feed_interrupted_osc(parser, terminal):
    """Test that the parser handles an OSC sequence interrupted by another escape."""
    # OSC sequence containing an escape, split across two feeds
    parser.feed("Hello \x1b]2;some text here\x1b[A")
    parser.feed("more text\x07world")

    assert "Hello world" in terminal.capture_pane()
    assert terminal.title == "some text here\x1b[Amore text"


def test_parser_feed_multiple_escapes(parser, terminal):
    """Test that the parser handles multiple escape characters correctly."""
    parser.feed("hello\x1b\x1b")
    assert "hello" in terminal.capture_pane()
    # The two escape characters should be consumed and dispatched as 'esc' events
    assert parser.buffer == ""


def test_parser_feed_simple_truncate(parser, terminal):
    """Test a simple truncated escape sequence."""
    parser.feed("hello\x1b")
    assert "hello" in terminal.capture_pane()
    assert parser.buffer == "\x1b"

    parser.feed("[1;1H")
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 0
    assert parser.buffer == ""
