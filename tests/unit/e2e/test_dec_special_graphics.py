"""Test DEC Special Graphics character set switching."""

from bittty.terminal import Terminal
from bittty.parser import Parser


def test_dec_special_graphics_box_drawing():
    """Test that ESC(0 switches to graphics mode and ESC(B switches back."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    # Draw a simple box using DEC Special Graphics
    # In graphics mode: l=┌, q=─, k=┐, x=│, m=└, j=┘
    parser.feed("\x1b(0")  # Switch to DEC Special Graphics
    parser.feed("lqqk\r\n")  # Top: ┌──┐
    parser.feed("x  x\r\n")  # Middle: │  │
    parser.feed("mqqj")  # Bottom: └──┘
    parser.feed("\x1b(B")  # Switch back to ASCII

    # Check that box drawing characters were used
    assert terminal.current_buffer.get_line_text(0) == "┌──┐      "
    assert terminal.current_buffer.get_line_text(1) == "│  │      "
    assert terminal.current_buffer.get_line_text(2) == "└──┘      "


def test_dec_special_graphics_full_mapping():
    """Test all DEC Special Graphics characters."""
    terminal = Terminal(width=20, height=10)
    parser = Parser(terminal)

    # Test various special characters
    # See: https://vt100.net/docs/vt100-ug/table3-9.html
    parser.feed("\x1b(0")  # Switch to graphics mode

    # Box drawing
    parser.feed("j")  # ┘ (lower right corner)
    parser.feed("k")  # ┐ (upper right corner)
    parser.feed("l")  # ┌ (upper left corner)
    parser.feed("m")  # └ (lower left corner)
    parser.feed("n")  # ┼ (crossing lines)
    parser.feed("q")  # ─ (horizontal line)
    parser.feed("t")  # ├ (left tee)
    parser.feed("u")  # ┤ (right tee)
    parser.feed("v")  # ┴ (bottom tee)
    parser.feed("w")  # ┬ (top tee)
    parser.feed("x")  # │ (vertical line)

    parser.feed("\x1b(B")  # Back to ASCII

    expected = "┘┐┌└┼─├┤┴┬│         "
    assert terminal.current_buffer.get_line_text(0) == expected


def test_dec_graphics_mode_persists():
    """Test that graphics mode persists until explicitly changed."""
    terminal = Terminal(width=10, height=5)
    parser = Parser(terminal)

    parser.feed("\x1b(0")  # Switch to graphics mode
    parser.feed("q")  # Should be ─
    parser.feed("\r\n")
    parser.feed("x")  # Should be │
    parser.feed("\r\n")
    # Still in graphics mode
    parser.feed("n")  # Should be ┼

    assert terminal.current_buffer.get_line_text(0) == "─         "
    assert terminal.current_buffer.get_line_text(1) == "│         "
    assert terminal.current_buffer.get_line_text(2) == "┼         "


def test_switch_between_modes():
    """Test switching between ASCII and graphics modes."""
    terminal = Terminal(width=15, height=3)
    parser = Parser(terminal)

    parser.feed("ABC")  # Normal ASCII
    parser.feed("\x1b(0")  # Switch to graphics
    parser.feed("lqk")  # Box drawing: ┌─┐
    parser.feed("\x1b(B")  # Back to ASCII
    parser.feed("DEF")  # Normal ASCII

    assert terminal.current_buffer.get_line_text(0) == "ABC┌─┐DEF      "


def test_graphics_mode_with_colors():
    """Test that colors work correctly with graphics mode."""
    terminal = Terminal(width=10, height=3)
    parser = Parser(terminal)

    parser.feed("\x1b[31m")  # Red
    parser.feed("\x1b(0")  # Graphics mode
    parser.feed("lqqk")  # Should be red box drawing
    parser.feed("\x1b(B")  # Back to ASCII
    parser.feed("\x1b[0m")  # Reset color

    # Check both the characters and that they have the red style
    assert terminal.current_buffer.get_line_text(0) == "┌──┐      "
    # Check first character has red foreground
    style, char = terminal.current_buffer.get_cell(0, 0)
    assert char == "┌"
    assert style.fg.mode == "indexed"
    assert style.fg.value == 1  # Red


def test_other_character_sets():
    """Test that other character set designators are handled."""
    terminal = Terminal(width=10, height=3)
    parser = Parser(terminal)

    # These should all switch back to normal ASCII/US
    parser.feed("\x1b(B")  # US ASCII
    parser.feed("ABC")
    parser.feed("\r\n")

    parser.feed("\x1b(A")  # UK - should also give normal ASCII for these chars
    parser.feed("DEF")
    parser.feed("\r\n")

    assert terminal.current_buffer.get_line_text(0) == "ABC       "
    assert terminal.current_buffer.get_line_text(1) == "DEF       "
