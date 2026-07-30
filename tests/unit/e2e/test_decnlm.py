"""Test DECNLM (Line Feed/New Line Mode) implementation."""

from bittty import Board
from bittty.parser import Parser


def test_decnlm_default_mode():
    """Test that line feed only moves cursor down by default (DECNLM disabled)."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Move cursor to column 5
    board.cursor.x = 5
    board.cursor.y = 1

    # Send line feed
    parser.feed("\n")

    # Should only move cursor down, not affect x position
    assert board.cursor.x == 5
    assert board.cursor.y == 2


def test_decnlm_enabled_cr_lf():
    """Test that when DECNLM is enabled, line feed also performs carriage return."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Enable LNM (CSI 20 h)
    parser.feed("\x1b[20h")

    # Move cursor to column 5
    board.cursor.x = 5
    board.cursor.y = 1

    # Send line feed
    parser.feed("\n")

    # Should move cursor down AND to column 0 (CR+LF behavior)
    assert board.cursor.x == 0
    assert board.cursor.y == 2


def test_decnlm_disabled_lf_only():
    """Test that when DECNLM is disabled, line feed only moves cursor down."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Enable DECNLM first
    parser.feed("\x1b[20h")

    # Then disable LNM (CSI 20 l)
    parser.feed("\x1b[20l")

    # Move cursor to column 5
    board.cursor.x = 5
    board.cursor.y = 1

    # Send line feed
    parser.feed("\n")

    # Should only move cursor down, not affect x position (LF only behavior)
    assert board.cursor.x == 5
    assert board.cursor.y == 2


def test_decnlm_multiple_line_feeds():
    """Test DECNLM behavior with multiple line feeds."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Enable DECNLM
    parser.feed("\x1b[20h")

    # Move cursor to column 7
    board.cursor.x = 7
    board.cursor.y = 0

    # Send multiple line feeds
    parser.feed("\n\n\n")

    # Should be at column 0, row 3 (each LF does CR+LF)
    assert board.cursor.x == 0
    assert board.cursor.y == 3


def test_decnlm_at_bottom_with_scrolling():
    """Test DECNLM behavior when line feed causes scrolling."""
    board = Board(width=10, height=3)
    parser = Parser(board)

    # Enable DECNLM
    parser.feed("\x1b[20h")

    # Move cursor to bottom row and some column
    board.cursor.x = 6
    board.cursor.y = 2  # Bottom row (0-indexed)

    # Send line feed - should scroll and reset cursor to column 0
    parser.feed("\n")

    # Should be at column 0, still at bottom row (scrolled)
    assert board.cursor.x == 0
    assert board.cursor.y == 2


def test_decnlm_explicit_carriage_return_unaffected():
    """Test that explicit carriage return is unaffected by DECNLM mode."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Enable DECNLM
    parser.feed("\x1b[20h")

    # Move cursor to column 5
    board.cursor.x = 5
    board.cursor.y = 1

    # Send explicit carriage return
    parser.feed("\r")

    # Should only move cursor to column 0, not affect y position
    assert board.cursor.x == 0
    assert board.cursor.y == 1


def test_decnlm_with_cr_lf_sequence():
    """Test DECNLM with explicit CR+LF sequence."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Test with DECNLM disabled first
    board.cursor.x = 5
    board.cursor.y = 1

    # Send CR+LF sequence
    parser.feed("\r\n")

    # Should be at column 0, next row
    assert board.cursor.x == 0
    assert board.cursor.y == 2

    # Now test with DECNLM enabled
    parser.feed("\x1b[20h")

    board.cursor.x = 5
    board.cursor.y = 2

    # Send CR+LF sequence (CR first, then LF with DECNLM)
    parser.feed("\r\n")

    # Should still be at column 0, next row (LF with DECNLM also does CR, but cursor already at 0)
    assert board.cursor.x == 0
    assert board.cursor.y == 3


def test_decnlm_mode_flag_state():
    """Test that the DECNLM mode flag is correctly set and unset."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Initially disabled
    assert board.modes.linefeed_newline_mode is False

    # Enable DECNLM
    parser.feed("\x1b[20h")
    assert board.modes.linefeed_newline_mode is True

    # Disable DECNLM
    parser.feed("\x1b[20l")
    assert board.modes.linefeed_newline_mode is False


def test_decnlm_wrapped_line_behavior():
    """Test DECNLM behavior when line wrapping occurs."""
    board = Board(width=5, height=3)
    parser = Parser(board)

    # Enable DECNLM
    parser.feed("\x1b[20h")

    # Write text that will wrap
    parser.feed("Hello")  # Fills first line

    # Cursor should be at end of line
    assert board.cursor.x == 5

    # Send line feed
    parser.feed("\n")

    # Should move to column 0 of next line
    assert board.cursor.x == 0
    assert board.cursor.y == 1


def test_decnlm_vertical_tab_default():
    """Test that vertical tab moves cursor down by default (DECNLM disabled)."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Move cursor to column 5
    board.cursor.x = 5
    board.cursor.y = 1

    # Send vertical tab (\x0b)
    parser.feed("\x0b")

    # Should only move cursor down, not affect x position
    assert board.cursor.x == 5
    assert board.cursor.y == 2


def test_decnlm_vertical_tab_enabled():
    """Test that when DECNLM is enabled, vertical tab also performs carriage return."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Enable LNM (CSI 20 h)
    parser.feed("\x1b[20h")

    # Move cursor to column 5
    board.cursor.x = 5
    board.cursor.y = 1

    # Send vertical tab (\x0b)
    parser.feed("\x0b")

    # Should move cursor down AND to column 0 (CR+LF behavior)
    assert board.cursor.x == 0
    assert board.cursor.y == 2


def test_decnlm_form_feed_default():
    """Test that form feed moves cursor down by default (DECNLM disabled)."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Move cursor to column 5
    board.cursor.x = 5
    board.cursor.y = 1

    # Send form feed (\x0c)
    parser.feed("\x0c")

    # Should only move cursor down, not affect x position
    assert board.cursor.x == 5
    assert board.cursor.y == 2


def test_decnlm_form_feed_enabled():
    """Test that when DECNLM is enabled, form feed also performs carriage return."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Enable LNM (CSI 20 h)
    parser.feed("\x1b[20h")

    # Move cursor to column 5
    board.cursor.x = 5
    board.cursor.y = 1

    # Send form feed (\x0c)
    parser.feed("\x0c")

    # Should move cursor down AND to column 0 (CR+LF behavior)
    assert board.cursor.x == 0
    assert board.cursor.y == 2


def test_decnlm_mixed_lf_vt_ff():
    """Test DECNLM behavior with mixed LF, VT, and FF characters."""
    board = Board(width=10, height=5)
    parser = Parser(board)

    # Enable DECNLM
    parser.feed("\x1b[20h")

    # Move cursor to column 5
    board.cursor.x = 5
    board.cursor.y = 0

    # Send LF, VT, FF sequence
    parser.feed("\n\x0b\x0c")

    # All should have moved cursor to column 0 and advanced by 3 rows
    assert board.cursor.x == 0
    assert board.cursor.y == 3
