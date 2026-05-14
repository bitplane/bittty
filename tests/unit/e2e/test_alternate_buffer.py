from bittty.constants import ALT_SCREEN_BUFFER, ESC


def test_alternate_buffer_enable(parser, terminal):
    """Test CSI ? 1049 h (Enable alternate terminal buffer)."""

    # Write some text to primary buffer
    parser.feed("Primary buffer text")
    primary_text = terminal.current_buffer.get_line_text(0).strip()
    assert "Primary buffer text" in primary_text

    # Enable alternate screen buffer
    parser.feed(f"{ESC}[?{ALT_SCREEN_BUFFER}h")

    # Should now be in alternate screen mode
    assert terminal.in_alt_screen

    # Write text to alternate buffer
    parser.feed("Alternate buffer text")
    alt_text = terminal.current_buffer.get_line_text(0).strip()
    assert "Alternate buffer text" in alt_text
    assert "Primary buffer text" not in alt_text


def test_alternate_buffer_disable(parser, terminal):
    """Test CSI ? 1049 l (Disable alternate terminal buffer)."""
    # Write to primary buffer
    parser.feed("Primary content")

    # Switch to alternate buffer
    parser.feed(f"{ESC}[?{ALT_SCREEN_BUFFER}h")
    parser.feed("Alt content")

    # Switch back to primary buffer
    parser.feed(f"{ESC}[?{ALT_SCREEN_BUFFER}l")

    # Should be back in primary screen mode
    assert not terminal.in_alt_screen

    # Primary buffer content should be restored
    primary_text = terminal.current_buffer.get_line_text(0).strip()
    assert "Primary content" in primary_text
    assert "Alt content" not in primary_text


def test_alternate_buffer_persistence(parser, terminal):
    """Test that buffers maintain their content when switching."""
    # Primary buffer setup
    parser.feed("Line 1 primary")
    parser.feed("\r\n")
    parser.feed("Line 2 primary")

    # Switch to alternate and add content
    # Note: cursor position is preserved when switching to alternate
    parser.feed(f"{ESC}[?{ALT_SCREEN_BUFFER}h")
    parser.feed("Alt line 1")
    parser.feed("\r\n")
    parser.feed("Alt line 2")

    # Switch back to primary
    parser.feed(f"{ESC}[?{ALT_SCREEN_BUFFER}l")

    # Verify primary content is intact
    line0 = terminal.current_buffer.get_line_text(0).strip()
    line1 = terminal.current_buffer.get_line_text(1).strip()
    assert "Line 1 primary" in line0
    assert "Line 2 primary" in line1

    # Switch back to alternate and verify its content
    parser.feed(f"{ESC}[?{ALT_SCREEN_BUFFER}h")

    # Content is preserved but appears at lines where it was written
    # (cursor was at line 1 when we switched to alt, so content is on lines 1 and 2)
    alt_line1 = terminal.current_buffer.get_line_text(1).strip()
    alt_line2 = terminal.current_buffer.get_line_text(2).strip()
    assert "Alt line 1" in alt_line1
    assert "Alt line 2" in alt_line2


def test_alternate_buffer_with_cursor_visibility(parser, terminal):
    """Test alternate buffer mode combined with cursor visibility."""
    # Multiple modes at once: cursor visibility + alternate buffer
    parser.feed("\x1b[?25;1049h")

    # Both modes should be set
    assert terminal.cursor_visible is True
    assert terminal.in_alt_screen is True


def test_alternate_buffer_mixed_operations(parser, terminal):
    """Test mixed set/reset operations on alternate buffer and other modes."""
    # Enable cursor + alternate buffer
    parser.feed("\x1b[?25;1049h")
    assert terminal.cursor_visible is True
    assert terminal.in_alt_screen is True

    # Disable cursor, keep alternate buffer enabled
    parser.feed("\x1b[?25l")
    assert terminal.cursor_visible is False
    assert terminal.in_alt_screen is True  # Still in alt screen

    # Disable alternate buffer
    parser.feed("\x1b[?1049l")
    assert terminal.in_alt_screen is False  # Back to primary
