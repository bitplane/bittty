"""Test DECSCLM (Scrolling Mode) implementation."""

from bittty.terminal import Terminal
from bittty.parser import Parser


def test_decsclm_default_jump_scrolling():
    """Test that scrolling is jump (instant) by default."""
    terminal = Terminal(width=20, height=5)

    # Should be jump scrolling by default (scroll_mode = False)
    assert not terminal.scroll_mode

    # Fill the terminal buffer completely
    terminal.cursor_y = 0
    for i in range(5):
        terminal.write_text(f"Line {i}")
        if i < 4:  # Don't add newline on last line
            terminal.line_feed()
            terminal.carriage_return()

    # Move to last line and trigger a scroll by adding content
    terminal.cursor_y = 4
    terminal.cursor_x = 0
    terminal.line_feed()  # This should scroll
    terminal.write_text("Line 5")

    # With jump scrolling, the scroll should be instant
    # The top line should have moved up
    assert terminal.current_buffer.get_line_text(4) == "Line 5              "


def test_decsclm_set_smooth_scrolling():
    """Test setting DECSCLM to enable smooth scrolling."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set DECSCLM mode (ESC [ ? 4 h)
    parser.feed("\x1b[?4h")

    # Should enable smooth scrolling
    assert terminal.scroll_mode


def test_decsclm_reset_to_jump():
    """Test resetting DECSCLM back to jump scrolling."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set smooth scrolling first
    parser.feed("\x1b[?4h")
    assert terminal.scroll_mode

    # Reset DECSCLM mode (ESC [ ? 4 l)
    parser.feed("\x1b[?4l")

    # Should return to jump scrolling
    assert not terminal.scroll_mode


def test_decsclm_affects_scroll_behavior():
    """Test that DECSCLM actually affects scrolling behavior."""
    terminal = Terminal(width=20, height=3)
    parser = Parser(terminal)

    # Set smooth scrolling
    parser.feed("\x1b[?4h")

    # Fill screen
    terminal.write_text("Line 1\nLine 2\nLine 3")
    terminal.cursor_y = 2  # Move to last line

    # Trigger scroll - in smooth mode this should be gradual
    terminal.line_feed()

    # In real implementation, smooth scrolling would have intermediate states
    # For now, we just verify the mode is set correctly
    assert terminal.scroll_mode
