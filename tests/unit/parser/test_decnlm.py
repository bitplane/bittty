"""Test DECNLM (Line Feed/New Line Mode) implementation."""

from bittty.terminal import Terminal
from bittty.parser import Parser


def test_decnlm_default_mode():
    """Test that line feed only moves cursor down by default (DECNLM disabled)."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Move cursor to column 5
    terminal.cursor_x = 5
    terminal.cursor_y = 1

    # Send line feed
    parser.feed("\n")

    # Should only move cursor down, not affect x position
    assert terminal.cursor_x == 5
    assert terminal.cursor_y == 2


def test_decnlm_enabled_cr_lf():
    """Test that when DECNLM is enabled, line feed also performs carriage return."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Enable DECNLM (ESC [ ? 20 h)
    parser.feed("\x1b[?20h")

    # Move cursor to column 5
    terminal.cursor_x = 5
    terminal.cursor_y = 1

    # Send line feed
    parser.feed("\n")

    # Should move cursor down AND to column 0 (CR+LF behavior)
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 2


def test_decnlm_disabled_lf_only():
    """Test that when DECNLM is disabled, line feed only moves cursor down."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Enable DECNLM first
    parser.feed("\x1b[?20h")

    # Then disable DECNLM (ESC [ ? 20 l)
    parser.feed("\x1b[?20l")

    # Move cursor to column 5
    terminal.cursor_x = 5
    terminal.cursor_y = 1

    # Send line feed
    parser.feed("\n")

    # Should only move cursor down, not affect x position (LF only behavior)
    assert terminal.cursor_x == 5
    assert terminal.cursor_y == 2


def test_decnlm_multiple_line_feeds():
    """Test DECNLM behavior with multiple line feeds."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Enable DECNLM
    parser.feed("\x1b[?20h")

    # Move cursor to column 7
    terminal.cursor_x = 7
    terminal.cursor_y = 0

    # Send multiple line feeds
    parser.feed("\n\n\n")

    # Should be at column 0, row 3 (each LF does CR+LF)
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 3


def test_decnlm_at_bottom_with_scrolling():
    """Test DECNLM behavior when line feed causes scrolling."""
    terminal = Terminal(width=10, height=3)
    parser = Parser(terminal)

    # Enable DECNLM
    parser.feed("\x1b[?20h")

    # Move cursor to bottom row and some column
    terminal.cursor_x = 6
    terminal.cursor_y = 2  # Bottom row (0-indexed)

    # Send line feed - should scroll and reset cursor to column 0
    parser.feed("\n")

    # Should be at column 0, still at bottom row (scrolled)
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 2


def test_decnlm_explicit_carriage_return_unaffected():
    """Test that explicit carriage return is unaffected by DECNLM mode."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Enable DECNLM
    parser.feed("\x1b[?20h")

    # Move cursor to column 5
    terminal.cursor_x = 5
    terminal.cursor_y = 1

    # Send explicit carriage return
    parser.feed("\r")

    # Should only move cursor to column 0, not affect y position
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 1


def test_decnlm_with_cr_lf_sequence():
    """Test DECNLM with explicit CR+LF sequence."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Test with DECNLM disabled first
    terminal.cursor_x = 5
    terminal.cursor_y = 1

    # Send CR+LF sequence
    parser.feed("\r\n")

    # Should be at column 0, next row
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 2

    # Now test with DECNLM enabled
    parser.feed("\x1b[?20h")

    terminal.cursor_x = 5
    terminal.cursor_y = 2

    # Send CR+LF sequence (CR first, then LF with DECNLM)
    parser.feed("\r\n")

    # Should still be at column 0, next row (LF with DECNLM also does CR, but cursor already at 0)
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 3


def test_decnlm_mode_flag_state():
    """Test that the DECNLM mode flag is correctly set and unset."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Initially disabled
    assert terminal.linefeed_newline_mode is False

    # Enable DECNLM
    parser.feed("\x1b[?20h")
    assert terminal.linefeed_newline_mode is True

    # Disable DECNLM
    parser.feed("\x1b[?20l")
    assert terminal.linefeed_newline_mode is False


def test_decnlm_wrapped_line_behavior():
    """Test DECNLM behavior when line wrapping occurs."""
    terminal = Terminal(width=5, height=3)
    parser = Parser(terminal)

    # Enable DECNLM
    parser.feed("\x1b[?20h")

    # Write text that will wrap
    parser.feed("Hello")  # Fills first line

    # Cursor should be at end of line
    assert terminal.cursor_x == 5

    # Send line feed
    parser.feed("\n")

    # Should move to column 0 of next line
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 1


def test_decnlm_vertical_tab_default():
    """Test that vertical tab moves cursor down by default (DECNLM disabled)."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Move cursor to column 5
    terminal.cursor_x = 5
    terminal.cursor_y = 1

    # Send vertical tab (\x0b)
    parser.feed("\x0b")

    # Should only move cursor down, not affect x position
    assert terminal.cursor_x == 5
    assert terminal.cursor_y == 2


def test_decnlm_vertical_tab_enabled():
    """Test that when DECNLM is enabled, vertical tab also performs carriage return."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Enable DECNLM (ESC [ ? 20 h)
    parser.feed("\x1b[?20h")

    # Move cursor to column 5
    terminal.cursor_x = 5
    terminal.cursor_y = 1

    # Send vertical tab (\x0b)
    parser.feed("\x0b")

    # Should move cursor down AND to column 0 (CR+LF behavior)
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 2


def test_decnlm_form_feed_default():
    """Test that form feed moves cursor down by default (DECNLM disabled)."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Move cursor to column 5
    terminal.cursor_x = 5
    terminal.cursor_y = 1

    # Send form feed (\x0c)
    parser.feed("\x0c")

    # Should only move cursor down, not affect x position
    assert terminal.cursor_x == 5
    assert terminal.cursor_y == 2


def test_decnlm_form_feed_enabled():
    """Test that when DECNLM is enabled, form feed also performs carriage return."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Enable DECNLM (ESC [ ? 20 h)
    parser.feed("\x1b[?20h")

    # Move cursor to column 5
    terminal.cursor_x = 5
    terminal.cursor_y = 1

    # Send form feed (\x0c)
    parser.feed("\x0c")

    # Should move cursor down AND to column 0 (CR+LF behavior)
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 2


def test_decnlm_mixed_lf_vt_ff():
    """Test DECNLM behavior with mixed LF, VT, and FF characters."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Enable DECNLM
    parser.feed("\x1b[?20h")

    # Move cursor to column 5
    terminal.cursor_x = 5
    terminal.cursor_y = 0

    # Send LF, VT, FF sequence
    parser.feed("\n\x0b\x0c")

    # All should have moved cursor to column 0 and advanced by 3 rows
    assert terminal.cursor_x == 0
    assert terminal.cursor_y == 3
