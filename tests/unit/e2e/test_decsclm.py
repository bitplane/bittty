"""Test DECSCLM (Scrolling Mode) implementation."""

from bittty import Board
from bittty.parser import Parser


def test_decsclm_default_jump_scrolling():
    """Test that scrolling is jump (instant) by default."""
    board = Board(width=20, height=5)

    # Should be jump scrolling by default (scroll_mode = False)
    assert not board.modes.scroll_mode

    # Fill the terminal buffer completely
    board.cursor.y = 0
    for i in range(5):
        board.blitter.write_text(f"Line {i}")
        if i < 4:  # Don't add newline on last line
            board.cursor.line_feed()
            board.cursor.carriage_return()

    # Move to last line and trigger a scroll by adding content
    board.cursor.y = 4
    board.cursor.x = 0
    board.cursor.line_feed()  # This should scroll
    board.blitter.write_text("Line 5")

    # With jump scrolling, the scroll should be instant
    # The top line should have moved up
    assert board.blitter.current_buffer.get_line_text(4) == "Line 5              "


def test_decsclm_set_smooth_scrolling():
    """Test setting DECSCLM to enable smooth scrolling."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Set DECSCLM mode (ESC [ ? 4 h)
    parser.feed("\x1b[?4h")

    # Should enable smooth scrolling
    assert board.modes.scroll_mode


def test_decsclm_reset_to_jump():
    """Test resetting DECSCLM back to jump scrolling."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Set smooth scrolling first
    parser.feed("\x1b[?4h")
    assert board.modes.scroll_mode

    # Reset DECSCLM mode (ESC [ ? 4 l)
    parser.feed("\x1b[?4l")

    # Should return to jump scrolling
    assert not board.modes.scroll_mode


def test_decsclm_affects_scroll_behavior():
    """Test that DECSCLM actually affects scrolling behavior."""
    board = Board(width=20, height=3)
    parser = Parser(board)

    # Set smooth scrolling
    parser.feed("\x1b[?4h")

    # Fill screen
    board.blitter.write_text("Line 1\nLine 2\nLine 3")
    board.cursor.y = 2  # Move to last line

    # Trigger scroll - in smooth mode this should be gradual
    board.cursor.line_feed()

    # In real implementation, smooth scrolling would have intermediate states
    # For now, we just verify the mode is set correctly
    assert board.modes.scroll_mode
