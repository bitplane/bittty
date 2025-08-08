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


def test_parser_feed_truncated_escape():
    """Test that the parser handles truncated escape sequences correctly."""

    # This is a simplified mock. In a real scenario, you'd have a more complete mock
    # or a real Terminal object.
    class MockTerminal:
        def __init__(self):
            self.written_text = ""
            self.application_keypad = False
            self.current_ansi_code = ""

        def write_text(self, text, code):
            self.written_text += text

    terminal = MockTerminal()
    parser = Parser(terminal)

    # Feed a chunk of text with a truncated escape sequence at the end
    parser.feed("hello\x1b")
    assert terminal.written_text == "hello"
    assert parser.buffer == "\x1b"

    # Feed the rest of the escape sequence
    parser.feed("[A")
    # This is a CSI sequence, which is handled by a different part of the parser.
    # For this test, we just want to ensure the buffer is cleared.
    assert parser.buffer == ""
