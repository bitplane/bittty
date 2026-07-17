from bittty.constants import (
    ESC,
    SGR_RESET,
    SGR_BOLD,
    SGR_NOT_BOLD_NOR_FAINT,
    SGR_NOT_ITALIC,
)


def test_sgr_reset_all_attributes(parser, board):
    """Test SGR 0 (Reset all attributes) clears all styling."""
    # Set some styling first
    parser.feed(f"{ESC}[1;3;4m")  # Bold, italic, underline
    # Check that bold, italic, underline parameters are in the ANSI code
    assert "1" in board.style.current_ansi_code  # Bold parameter
    assert "3" in board.style.current_ansi_code  # Italic parameter
    assert "4" in board.style.current_ansi_code  # Underline parameter
    assert board.style.current_ansi_code == "\x1b[1;3;4m"  # Expected format

    # Reset should clear everything
    parser.feed(f"{ESC}[{SGR_RESET}m")
    assert board.style.current_ansi_code == ""


def test_sgr_bold_styling(parser, board):
    """Test SGR 1 (Bold) and SGR 22 (Not bold) with actual text."""
    # Apply bold and write text
    parser.feed(f"{ESC}[{SGR_BOLD}m")
    parser.feed("Bold text")

    # Verify bold is active and text was written
    assert "1" in board.style.current_ansi_code  # Bold parameter
    line_text = board.blitter.current_buffer.get_line_text(0).strip()
    assert "Bold text" in line_text

    # Remove bold
    parser.feed(f"{ESC}[{SGR_NOT_BOLD_NOR_FAINT}m")
    assert "1" not in board.style.current_ansi_code  # Bold should be removed

    # Write more text
    parser.feed(" Normal text")
    line_text = board.blitter.current_buffer.get_line_text(0).strip()
    assert "Bold text Normal text" in line_text


def test_sgr_multiple_attributes(parser, board):
    """Test combining multiple SGR attributes."""
    # Apply multiple attributes at once
    parser.feed(f"{ESC}[1;3;4;5m")  # Bold, italic, underline, blink

    # All should be present
    assert "1" in board.style.current_ansi_code  # Bold
    assert "3" in board.style.current_ansi_code  # Italic
    assert "4" in board.style.current_ansi_code  # Underline
    assert "5" in board.style.current_ansi_code  # Blink

    # Write styled text
    parser.feed("Styled text")
    line_text = board.blitter.current_buffer.get_line_text(0).strip()
    assert "Styled text" in line_text


def test_sgr_color_codes(parser, board):
    """Test SGR color codes (30-37 foreground, 40-47 background)."""
    # Set red foreground and blue background
    parser.feed(f"{ESC}[31;44m")

    assert "31" in board.style.current_ansi_code  # Red foreground
    assert "44" in board.style.current_ansi_code  # Blue background

    parser.feed("Colored text")
    line_text = board.blitter.current_buffer.get_line_text(0).strip()
    assert "Colored text" in line_text

    # Reset colors
    parser.feed(f"{ESC}[39;49m")  # Default fg/bg
    # After reset, colors should be gone (default colors don't appear in ANSI)
    assert board.style.current_ansi_code == ""


def test_sgr_256_color_support(parser, board):
    """Test 256-color SGR sequences."""
    # 256-color foreground (38;5;n) and background (48;5;n)
    parser.feed(f"{ESC}[38;5;196;48;5;21m")  # Bright red fg, bright blue bg

    # Should contain the 256-color sequences
    assert "38;5;196" in board.style.current_ansi_code  # 256-color foreground
    assert "48;5;21" in board.style.current_ansi_code  # 256-color background

    parser.feed("256-color text")
    line_text = board.blitter.current_buffer.get_line_text(0).strip()
    assert "256-color text" in line_text


def test_sgr_rgb_color_support(parser, board):
    """Test RGB SGR sequences."""
    # RGB foreground (38;2;r;g;b) and background (48;2;r;g;b)
    parser.feed(f"{ESC}[38;2;255;0;0;48;2;0;0;255m")  # Red fg, blue bg

    # Should contain the RGB sequences
    assert "38;2;255;0;0" in board.style.current_ansi_code  # RGB foreground
    assert "48;2;0;0;255" in board.style.current_ansi_code  # RGB background

    parser.feed("RGB text")
    line_text = board.blitter.current_buffer.get_line_text(0).strip()
    assert "RGB text" in line_text


def test_sgr_style_inheritance(parser, board):
    """Test that styles are inherited by subsequent text."""
    # Set initial styling
    parser.feed(f"{ESC}[1;31m")  # Bold red
    parser.feed("Red bold")

    # Add more styling
    parser.feed(f"{ESC}[4m")  # Add underline
    parser.feed(" underlined")

    # Should still have bold + red + underline
    assert "1" in board.style.current_ansi_code  # Bold
    assert "31" in board.style.current_ansi_code  # Red
    assert "4" in board.style.current_ansi_code  # Underline

    line_text = board.blitter.current_buffer.get_line_text(0).strip()
    assert "Red bold underlined" in line_text


def test_sgr_selective_reset(parser, board):
    """Test resetting specific attributes while keeping others."""
    # Apply multiple styles
    parser.feed(f"{ESC}[1;3;4;31m")  # Bold, italic, underline, red

    # Remove just italic
    parser.feed(f"{ESC}[{SGR_NOT_ITALIC}m")

    # Should still have bold, underline, red (but not italic)
    expected = "\x1b[1;4;31m"  # Bold, underline, red (no italic)
    assert board.style.current_ansi_code == expected


def test_sgr_reset_mid_sequence_clears_prior_attributes(parser, board):
    """ESC[0;31m means "reset, then red" — the 0 must not be lost in a merge."""
    parser.feed(f"{ESC}[1;4m")  # bold + underline
    parser.feed(f"{ESC}[0;31m")

    style = board.style.current
    assert style.bold is None
    assert style.underline is None
    assert style.fg is not None and style.fg.value == 1  # red


def test_sgr_empty_leading_parameter_is_a_reset(parser, board):
    """ESC[;31m — an empty parameter defaults to 0, which is a reset."""
    parser.feed(f"{ESC}[1m")
    parser.feed(f"{ESC}[;31m")

    style = board.style.current
    assert style.bold is None
    assert style.fg is not None and style.fg.value == 1


def test_sgr_trailing_empty_parameter_resets(parser, board):
    """ESC[31;m applies red then reset — the net effect is a full reset."""
    parser.feed(f"{ESC}[1;31;m")

    style = board.style.current
    assert style.bold is None
    assert style.fg is None


def test_sgr_zero_colour_channels_are_not_resets(parser, board):
    """The 0s inside 38;2;0;0;0 are colour channels, not reset tokens."""
    parser.feed(f"{ESC}[1m")
    parser.feed(f"{ESC}[38;2;0;0;0m")

    style = board.style.current
    assert style.bold is True  # survived: no reset happened
    assert style.fg is not None and style.fg.value == (0, 0, 0)


def test_sgr_rapid_blink_maps_to_blink(parser, board):
    """SGR 6 (rapid blink) renders as blink."""
    parser.feed(f"{ESC}[6m")
    assert board.style.current.blink is True
