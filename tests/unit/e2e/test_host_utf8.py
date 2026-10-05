"""The host line is bytes: the board decodes UTF-8 however the child's output is chunked."""

import pytest

from bittty import Board


def _feed_in_chunks(data: bytes, size: int, width: int = 80) -> Board:
    board = Board(width=width, height=4)
    for start in range(0, len(data), size):
        board.feed_host_data(data[start : start + size])
    return board


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 11, 13])
@pytest.mark.parametrize(
    "text",
    ["🚽🪠💩" * 10, "Hello 世界 🌍 Testing 123", "ASCII text 中文字符 emoji: 😀🎉 back to ASCII"],
)
def test_characters_split_across_reads_are_reassembled(text, size):
    assert _feed_in_chunks(text.encode(), size).capture_text() == text


@pytest.mark.parametrize(
    "invalid",
    [
        b"\x80",  # stray continuation byte
        b"\xc0\x80",  # overlong encoding
        b"\xe0\x80\x80",  # invalid three-byte form
        b"\xf0\x80\x80\x80",  # invalid four-byte form
        b"\xff",  # invalid start byte
        b"\xc2",  # truncated two-byte character
        b"\xe0\xa0",  # truncated three-byte character
        b"\xf0\x90\x80",  # truncated four-byte character
        b"\xed\xa0\x80",  # UTF-16 surrogate
        b"\xf4\x90\x80\x80",  # beyond U+10FFFF
    ],
)
def test_undecodable_bytes_become_replacement_characters(invalid):
    data = invalid * 3 + b"!"
    assert _feed_in_chunks(data, 1).capture_text() == data.decode(errors="replace")


def test_a_truncated_character_waits_for_the_rest():
    board = Board(width=20, height=2)
    encoded = "Test 世".encode()
    board.feed_host_data(encoded[:-1])
    assert board.capture_text() == "Test"
    board.feed_host_data(encoded[-1:])
    assert board.capture_text() == "Test 世"
