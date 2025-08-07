from bittty.constants import (
    ESC,
    SGR_RESET,
    SGR_BOLD,
    SGR_NOT_BOLD_NOR_FAINT,
    SGR_NOT_ITALIC,
)


def test_sgr_reset_all_attributes(parser, terminal):
    """Test SGR 0 (Reset all attributes) clears all styling."""
    # Set some styling first
    parser.feed(f"{ESC}[1;3;4m")  # Bold, italic, underline
    # Check that bold, italic, underline parameters are in the ANSI code
    assert "1" in terminal.current_ansi_code  # Bold parameter
    assert "3" in terminal.current_ansi_code  # Italic parameter
    assert "4" in terminal.current_ansi_code  # Underline parameter
    assert terminal.current_ansi_code == "\x1b[1;3;4m"  # Expected format

    # Reset should clear everything
    parser.feed(f"{ESC}[{SGR_RESET}m")
    assert terminal.current_ansi_code == ""


def test_sgr_bold_styling(parser, terminal):
    """Test SGR 1 (Bold) and SGR 22 (Not bold) with actual text."""
    # Apply bold and write text
    parser.feed(f"{ESC}[{SGR_BOLD}m")
    parser.feed("Bold text")

    # Verify bold is active and text was written
    assert "1" in terminal.current_ansi_code  # Bold parameter
    line_text = terminal.current_buffer.get_line_text(0).strip()
    assert "Bold text" in line_text

    # Remove bold
    parser.feed(f"{ESC}[{SGR_NOT_BOLD_NOR_FAINT}m")
    assert "1" not in terminal.current_ansi_code  # Bold should be removed

    # Write more text
    parser.feed(" Normal text")
    line_text = terminal.current_buffer.get_line_text(0).strip()
    assert "Bold text Normal text" in line_text


def test_sgr_multiple_attributes(parser, terminal):
    """Test combining multiple SGR attributes."""
    # Apply multiple attributes at once
    parser.feed(f"{ESC}[1;3;4;5m")  # Bold, italic, underline, blink

    # All should be present
    assert "1" in terminal.current_ansi_code  # Bold
    assert "3" in terminal.current_ansi_code  # Italic
    assert "4" in terminal.current_ansi_code  # Underline
    assert "5" in terminal.current_ansi_code  # Blink

    # Write styled text
    parser.feed("Styled text")
    line_text = terminal.current_buffer.get_line_text(0).strip()
    assert "Styled text" in line_text


def test_sgr_color_codes(parser, terminal):
    """Test SGR color codes (30-37 foreground, 40-47 background)."""
    # Set red foreground and blue background
    parser.feed(f"{ESC}[31;44m")

    assert "31" in terminal.current_ansi_code  # Red foreground
    assert "44" in terminal.current_ansi_code  # Blue background

    parser.feed("Colored text")
    line_text = terminal.current_buffer.get_line_text(0).strip()
    assert "Colored text" in line_text

    # Reset colors
    parser.feed(f"{ESC}[39;49m")  # Default fg/bg
    # After reset, colors should be gone (default colors don't appear in ANSI)
    assert terminal.current_ansi_code == ""


def test_sgr_256_color_support(parser, terminal):
    """Test 256-color SGR sequences."""
    # 256-color foreground (38;5;n) and background (48;5;n)
    parser.feed(f"{ESC}[38;5;196;48;5;21m")  # Bright red fg, bright blue bg

    # Should contain the 256-color sequences
    assert "38;5;196" in terminal.current_ansi_code  # 256-color foreground
    assert "48;5;21" in terminal.current_ansi_code  # 256-color background

    parser.feed("256-color text")
    line_text = terminal.current_buffer.get_line_text(0).strip()
    assert "256-color text" in line_text


def test_sgr_rgb_color_support(parser, terminal):
    """Test RGB SGR sequences."""
    # RGB foreground (38;2;r;g;b) and background (48;2;r;g;b)
    parser.feed(f"{ESC}[38;2;255;0;0;48;2;0;0;255m")  # Red fg, blue bg

    # Should contain the RGB sequences
    assert "38;2;255;0;0" in terminal.current_ansi_code  # RGB foreground
    assert "48;2;0;0;255" in terminal.current_ansi_code  # RGB background

    parser.feed("RGB text")
    line_text = terminal.current_buffer.get_line_text(0).strip()
    assert "RGB text" in line_text


def test_sgr_style_inheritance(parser, terminal):
    """Test that styles are inherited by subsequent text."""
    # Set initial styling
    parser.feed(f"{ESC}[1;31m")  # Bold red
    parser.feed("Red bold")

    # Add more styling
    parser.feed(f"{ESC}[4m")  # Add underline
    parser.feed(" underlined")

    # Should still have bold + red + underline
    assert "1" in terminal.current_ansi_code  # Bold
    assert "31" in terminal.current_ansi_code  # Red
    assert "4" in terminal.current_ansi_code  # Underline

    line_text = terminal.current_buffer.get_line_text(0).strip()
    assert "Red bold underlined" in line_text


def test_sgr_selective_reset(parser, terminal):
    """Test resetting specific attributes while keeping others."""
    # Apply multiple styles
    parser.feed(f"{ESC}[1;3;4;31m")  # Bold, italic, underline, red

    # Remove just italic
    parser.feed(f"{ESC}[{SGR_NOT_ITALIC}m")

    # Should still have bold, underline, red (but not italic)
    expected = "\x1b[1;4;31m"  # Bold, underline, red (no italic)
    assert terminal.current_ansi_code == expected
