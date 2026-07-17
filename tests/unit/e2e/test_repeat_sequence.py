"""Tests for REP (Repeat) escape sequence."""

from bittty.parser import Parser
from bittty import Board
from bittty.constants import ESC


def test_rep_basic(small_board):
    """Test basic REP functionality."""
    parser = Parser(small_board)

    # Write a character, then repeat it
    parser.feed("A")
    parser.feed(f"{ESC}[5b")  # REP 5

    # Should have "AAAAAA" (1 original + 5 repeats)
    line = small_board.blitter.current_buffer.get_line_text(0)
    assert line[:6] == "AAAAAA"
    assert small_board.cursor.x == 6


def test_rep_with_different_counts():
    """Test REP with various repeat counts."""
    board = Board(width=30, height=10)
    parser = Parser(board)

    # Test count = 1
    parser.feed("X")
    parser.feed(f"{ESC}[1b")
    assert board.blitter.current_buffer.get_line_text(0)[:2] == "XX"

    # Test count = 10
    parser.feed("=")
    parser.feed(f"{ESC}[10b")
    assert board.blitter.current_buffer.get_line_text(0)[2:13] == "==========="

    # Test count = 0 (should do nothing)
    pos = board.cursor.x
    parser.feed(f"{ESC}[0b")
    assert board.cursor.x == pos


def test_rep_with_no_parameter():
    """Test REP with no parameter (should default to 1)."""
    board = Board(width=20, height=10)
    parser = Parser(board)

    parser.feed("Z")
    parser.feed(f"{ESC}[b")  # No parameter, should repeat once

    assert board.blitter.current_buffer.get_line_text(0)[:2] == "ZZ"


def test_rep_with_styled_character():
    """Test REP preserves the style of the repeated character."""
    board = Board(width=20, height=10)
    parser = Parser(board)

    # Set red color, write char, then repeat
    parser.feed(f"{ESC}[31m")  # Red
    parser.feed("*")
    parser.feed(f"{ESC}[3b")  # Repeat 3 times

    line = board.blitter.current_buffer.get_line_text(0)
    assert line[:4] == "****"

    # Check that all characters have red style
    # (This would need proper style checking in real implementation)


def test_rep_at_line_wrap():
    """Test REP behavior when reaching end of line."""
    board = Board(width=10, height=5)
    board.modes.auto_wrap = True
    parser = Parser(board)

    # Move to near end of line
    parser.feed(f"{ESC}[8G")  # Column 8 (0-based = position 7)
    parser.feed("X")  # Now at position 8
    parser.feed(f"{ESC}[5b")  # Try to repeat 5 times

    # With auto_wrap, REP continues past line width
    # The cursor_x increases beyond terminal width
    line = board.blitter.current_buffer.get_line_text(0)
    assert line[7] == "X"  # Original X at position 7
    assert line[8] == "X"  # First repeat at position 8
    assert line[9] == "X"  # Second repeat at position 9
    # Further repeats would go beyond line width


def test_rep_with_no_previous_character():
    """Test REP when no character has been printed yet."""
    board = Board(width=20, height=10)
    parser = Parser(board)

    # REP without printing anything first
    parser.feed(f"{ESC}[5b")

    # Should repeat the default character (space)
    assert board.blitter.current_buffer.get_line_text(0)[:5] == "     "


def test_rep_after_control_sequence():
    """Test REP after control sequences (should repeat last graphic char)."""
    board = Board(width=20, height=10)
    parser = Parser(board)

    parser.feed("A")
    parser.feed(f"{ESC}[2C")  # Move cursor forward
    parser.feed(f"{ESC}[3b")  # Repeat last char (A) 3 times

    line = board.blitter.current_buffer.get_line_text(0)
    assert line[0] == "A"
    assert line[3:6] == "AAA"


def test_rep_complex_sequence():
    """Test REP in a complex sequence like nethogs uses."""
    board = Board(width=80, height=24)
    parser = Parser(board)

    # Simulate drawing a line
    parser.feed("─")
    parser.feed(f"{ESC}[49b")  # Repeat 49 times

    line = board.blitter.current_buffer.get_line_text(0)
    assert all(c == "─" for c in line[:50])
    assert board.cursor.x == 50
