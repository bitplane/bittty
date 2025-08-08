"""Test PTY UTF-8 handling and buffering."""

import io
import pytest
from bittty.pty import PTY


def test_utf8_split_bytes_reconstruction():
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


@pytest.mark.parametrize("buffer_size", [1, 2, 3, 5, 7, 11, 13])
def test_utf8_various_buffer_sizes(buffer_size):
    """Test UTF-8 handling with various buffer sizes."""
    test_string = "Hello 世界 🌍 Testing 123"
    test_bytes = test_string.encode("utf-8")

    input_stream = io.BytesIO(test_bytes)
    pty = PTY(from_process=input_stream)

    result = ""
    for _ in range(len(test_bytes) * 2):
        chunk = pty.read(buffer_size)
        result += chunk

    assert result == test_string, f"Failed with buffer size {buffer_size}"
    assert "�" not in result

    pty.close()


def test_utf8_mixed_content():
    """Test PTY handles mixed ASCII and multi-byte UTF-8."""
    test_string = "ASCII text 中文字符 emoji: 😀🎉 back to ASCII"
    test_bytes = test_string.encode("utf-8")

    input_stream = io.BytesIO(test_bytes)
    pty = PTY(from_process=input_stream)

    # Read in small chunks
    result = ""
    while True:
        chunk = pty.read(5)
        if not chunk:
            break
        result += chunk

    assert result == test_string
    assert "�" not in result

    pty.close()


def test_utf8_empty_reads():
    """Test PTY handles empty reads correctly."""
    pty = PTY(from_process=io.BytesIO(b""))

    result = pty.read(100)
    assert result == ""

    pty.close()


@pytest.mark.parametrize(
    "name,invalid_sequence",
    [
        ("invalid_continuation_byte", b"\x80"),
        ("overlong_encoding", b"\xc0\x80"),
        ("invalid_3byte", b"\xe0\x80\x80"),
        ("invalid_4byte", b"\xf0\x80\x80\x80"),
        ("invalid_start_byte", b"\xff"),
        ("incomplete_2byte", b"\xc2"),
        ("incomplete_3byte", b"\xe0\xa0"),
        ("incomplete_4byte", b"\xf0\x90\x80"),
        ("utf16_surrogate", b"\xed\xa0\x80"),
        ("codepoint_too_large", b"\xf4\x90\x80\x80"),
    ],
)
def test_undecodable_characters(name, invalid_sequence):
    """Test PTY handles undecodable byte sequences correctly."""
    # Repeat the invalid sequence
    repeat_count = 3
    test_bytes = invalid_sequence * repeat_count
    input_stream = io.BytesIO(test_bytes)
    pty = PTY(from_process=input_stream)
    expected = test_bytes.decode("utf-8", errors="replace")

    # Read with buffer size 1 to stress-test the buffering
    result = ""
    for _ in range(len(test_bytes) * 2):
        chunk = pty.read(1)
        result += chunk

    # Should match what Python's decode with errors='replace' produces
    expected = test_bytes.decode("utf-8", errors="replace")
    assert result == expected, f"{name}: Expected {repr(expected)}, got {repr(result)}"

    pty.close()


def test_utf8_partial_sequence_at_end():
    """Test PTY buffers incomplete UTF-8 sequence at end of stream."""
    # Create a truncated UTF-8 sequence (first 2 bytes of 3-byte char)
    truncated_bytes = "Test 世".encode("utf-8")[:-1]

    input_stream = io.BytesIO(truncated_bytes)
    pty = PTY(from_process=input_stream)

    result = pty.read(100)
    # Should only get "Test " since the last character is incomplete
    assert result == "Test "
    assert "�" not in result

    # The incomplete bytes should be in the buffer
    assert len(pty._buffer) > 0

    pty.close()
