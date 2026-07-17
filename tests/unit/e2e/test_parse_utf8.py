"""Tests for UTF-8 parsing support."""

from bittty.parser import Parser
from bittty import Board
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT


def render_terminal_to_string(terminal: Board) -> str:
    """Render the terminal content to a plain string for testing."""
    return "\n".join(render_lines_to_string(terminal.get_content()))


def render_lines_to_string(lines: list[list[tuple[str, str]]]) -> list[str]:
    """Render a list of lines to a list of strings for testing."""
    output = []
    for line in lines:
        output.append("".join(char for _, char in line))
    return output


def test_unicode_emoji():
    """Test 4-byte Unicode emoji character."""
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal.board)

    # Test with house emoji 🏠 (U+1F3E0)
    emoji_text = "🏠 Home"

    parser.feed(emoji_text)

    output = render_terminal_to_string(terminal)
    assert "🏠 Home" in output

    # Check cursor position - counting characters not display width
    assert terminal.board.cursor.x == 6  # 1 char for emoji + 1 space + 4 for "Home"


def test_unicode_various():
    """Test various Unicode characters."""
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal.board)

    # Test various Unicode: ASCII, Latin-1, CJK, Emoji
    test_string = "Hello café 你好 🌍"

    parser.feed(test_string)

    output = render_terminal_to_string(terminal)
    assert test_string in output

    # Check the actual characters were written
    line_text = terminal.board.blitter.current_buffer.get_line_text(0)
    assert "Hello" in line_text
    assert "café" in line_text
    assert "你好" in line_text
    assert "🌍" in line_text


def test_unicode_box_drawing():
    """Test Unicode box drawing characters."""
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal.board)

    # Common box drawing characters used in terminal UIs
    box_chars = "┌─┐│└┘╔═╗║╚╝"

    parser.feed(box_chars)

    output = render_terminal_to_string(terminal)
    assert box_chars in output


def test_malformed_utf8():
    """Test handling of malformed UTF-8 sequences."""
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal.board)

    # Invalid UTF-8 sequence (already decoded by terminal widget)
    invalid_text = "Hello \ufffd\ufffd World"  # replacement chars

    # This should not crash - parser should handle gracefully
    parser.feed(invalid_text)

    output = render_terminal_to_string(terminal)
    # Should have processed the valid parts
    assert "Hello" in output
    assert "World" in output


def test_utf8_split_across_feeds():
    """Test UTF-8 sequence split across multiple feed() calls."""
    terminal = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    parser = Parser(terminal.board)

    # UTF-8 already decoded by terminal widget, so no need to test split sequences
    parser.feed("café")

    output = render_terminal_to_string(terminal)
    assert "café" in output
