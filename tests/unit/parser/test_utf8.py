"""Test UTF-8 handling through PTY layer."""

import io
from bittty.pty import PTY


def test_utf8_through_dummy_pty_with_split_bytes():
    """Test that UTF-8 bytes split across reads are reconstructed properly."""

    # Test data: toilet, plunger, poop emojis repeated
    test_string = "🚽🪠💩" * 10
    test_bytes = test_string.encode("utf-8")

    # Create a BytesIO with the test data
    input_stream = io.BytesIO(test_bytes)
    pty = PTY(from_process=input_stream)

    # Read with small buffer to force UTF-8 splits
    result = ""
    while True:
        # Read 7 bytes at a time (prime number to ensure splits)
        chunk = pty.read(7)
        if not chunk:
            break
        result += chunk

    # This should reconstruct all UTF-8 properly, no replacement chars
    assert result == test_string
    assert "�" not in result  # No replacement characters
    assert "🚽🪠💩" * 10 == result

    pty.close()


def test_utf8_through_parser_with_dummy_pty(parser, terminal):
    """Test that UTF-8 characters work correctly through parser with DummyPTY."""

    # Test data: toilet, plunger, poop emojis repeated
    test_string = "🚽🪠💩" * 10

    # Create DummyPTY and inject the test data
    input_stream = io.BytesIO(test_string.encode("utf-8"))
    pty = PTY(from_process=input_stream)

    # Read from PTY and feed to parser (simulating terminal behavior)
    while True:
        chunk = pty.read(1024)  # Read in chunks
        if not chunk:
            break
        parser.feed(chunk)

    # Verify all the emojis made it through intact
    output = terminal.capture_pane()
    assert "🚽🪠💩" * 10 in output

    pty.close()


def test_utf8_through_parser(parser, terminal):
    """Test that UTF-8 characters work correctly through the parser directly."""
    # Test data: toilet, plunger, poop emojis repeated
    test_string = "🚽🪠💩" * 10

    # Feed the complete Unicode string to the parser
    # This is what actually happens - PTY decodes bytes to Unicode
    parser.feed(test_string)

    # Verify all the emojis made it through intact
    output = terminal.capture_pane()
    assert "🚽🪠💩" * 10 in output
