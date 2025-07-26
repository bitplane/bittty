"""Test comprehensive character set switching functionality."""

from bittty.terminal import Terminal
from bittty.parser import Parser


def test_g1_designation_and_switching():
    """Test G1 character set designation and switching."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G1 to DEC Special Graphics
    parser.feed("\x1b)0")  # ESC ) 0

    # Normal text in G0
    parser.feed("ABC")

    # Switch to G1 (Shift Out)
    parser.feed("\x0e")  # SO
    parser.feed("lqk")  # Should be box drawing

    # Switch back to G0 (Shift In)
    parser.feed("\x0f")  # SI
    parser.feed("DEF")

    assert terminal.current_buffer.get_line_text(0) == "ABC┌─┐DEF           "


def test_g2_g3_designation():
    """Test G2 and G3 character set designation."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G2 to DEC Special Graphics
    parser.feed("\x1b*0")  # ESC * 0

    # Set G3 to UK character set
    parser.feed("\x1b+A")  # ESC + A

    # Verify the character sets were set
    assert terminal.g2_charset == "0"
    assert terminal.g3_charset == "A"


def test_single_shift_2():
    """Test Single Shift 2 (SS2) for temporary G2 usage."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G2 to DEC Special Graphics
    parser.feed("\x1b*0")  # ESC * 0

    # Write normal character
    parser.feed("A")

    # Single shift to G2 for one character
    parser.feed("\x1bN")  # ESC N (SS2)
    parser.feed("l")  # Should be ┌ from G2

    # Back to normal G0
    parser.feed("B")

    assert terminal.current_buffer.get_line_text(0) == "A┌B                 "


def test_single_shift_3():
    """Test Single Shift 3 (SS3) for temporary G3 usage."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G3 to UK character set
    parser.feed("\x1b+A")  # ESC + A

    # Write normal character
    parser.feed("A")

    # Single shift to G3 for one character
    parser.feed("\x1bO")  # ESC O (SS3)
    parser.feed("#")  # Should be £ from UK set

    # Back to normal G0
    parser.feed("B")

    assert terminal.current_buffer.get_line_text(0) == "A£B                 "


def test_multiple_single_shifts():
    """Test multiple single shifts in sequence."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G2 to DEC Special Graphics
    parser.feed("\x1b*0")  # ESC * 0

    # Set G3 to UK character set
    parser.feed("\x1b+A")  # ESC + A

    parser.feed("A")

    # SS2 for one character
    parser.feed("\x1bN")  # ESC N (SS2)
    parser.feed("l")  # ┌ from G2

    # SS3 for one character
    parser.feed("\x1bO")  # ESC O (SS3)
    parser.feed("#")  # £ from G3

    # SS2 again
    parser.feed("\x1bN")  # ESC N (SS2)
    parser.feed("k")  # ┐ from G2

    parser.feed("B")

    assert terminal.current_buffer.get_line_text(0) == "A┌£┐B               "


def test_si_so_switching():
    """Test Shift In/Shift Out switching between G0 and G1."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G1 to DEC Special Graphics
    parser.feed("\x1b)0")  # ESC ) 0

    # Start in G0
    parser.feed("A")

    # Switch to G1
    parser.feed("\x0e")  # SO
    parser.feed("lqk")  # Box drawing

    # Switch back to G0
    parser.feed("\x0f")  # SI
    parser.feed("B")

    # Switch to G1 again
    parser.feed("\x0e")  # SO
    parser.feed("mjq")  # More box drawing

    # Back to G0
    parser.feed("\x0f")  # SI
    parser.feed("C")

    assert terminal.current_buffer.get_line_text(0) == "A┌─┐B└┘─C           "


def test_persistent_charset_state():
    """Test that character set state persists until changed."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G1 to DEC Special Graphics
    parser.feed("\x1b)0")  # ESC ) 0

    # Switch to G1
    parser.feed("\x0e")  # SO

    # All characters should be from DEC graphics
    parser.feed("lqqk\r\n")
    parser.feed("x  x\r\n")
    parser.feed("mqqj")

    assert terminal.current_buffer.get_line_text(0) == "┌──┐                "
    assert terminal.current_buffer.get_line_text(1) == "│  │                "
    assert terminal.current_buffer.get_line_text(2) == "└──┘                "


def test_mixed_character_sets():
    """Test complex mixing of multiple character sets."""
    terminal = Terminal(width=30, height=5)
    parser = Parser(terminal)

    # Set all character sets
    parser.feed("\x1b(B")  # G0 = US ASCII (default)
    parser.feed("\x1b)0")  # G1 = DEC Special Graphics
    parser.feed("\x1b*A")  # G2 = UK National
    parser.feed("\x1b+0")  # G3 = DEC Special Graphics

    # Complex sequence using all sets
    parser.feed("Text")  # G0 ASCII

    parser.feed("\x0e")  # Switch to G1
    parser.feed("lq")  # G1 graphics: ┌─

    parser.feed("\x0f")  # Switch back to G0
    parser.feed(" ")  # G0 space

    parser.feed("\x1bN")  # SS2
    parser.feed("#")  # G2 UK: £

    parser.feed(" ")  # G0 space

    parser.feed("\x1bO")  # SS3
    parser.feed("k")  # G3 graphics: ┐

    parser.feed("\x0e")  # Switch to G1
    parser.feed("j")  # G1 graphics: ┘

    parser.feed("\x0f")  # Back to G0
    parser.feed(" End")  # G0 ASCII

    assert terminal.current_buffer.get_line_text(0) == "Text┌─ £ ┐┘ End               "


def test_charset_with_colors():
    """Test character sets work with color changes."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G1 to DEC Special Graphics
    parser.feed("\x1b)0")

    # Red color + G1 graphics
    parser.feed("\x1b[31m")  # Red
    parser.feed("\x0e")  # Switch to G1
    parser.feed("lqqk")  # Red box drawing

    # Blue color + G0 text
    parser.feed("\x1b[34m")  # Blue
    parser.feed("\x0f")  # Switch to G0
    parser.feed("TEXT")  # Blue text

    # Check characters
    assert terminal.current_buffer.get_line_text(0) == "┌──┐TEXT            "

    # Check colors
    style, char = terminal.current_buffer.get_cell(0, 0)
    assert char == "┌"
    assert style.fg.value == 1  # Red

    style, char = terminal.current_buffer.get_cell(4, 0)
    assert char == "T"
    assert style.fg.value == 4  # Blue


def test_charset_reset_on_esc_c():
    """Test that ESC c resets character sets to defaults."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set non-default character sets
    parser.feed("\x1b)0")  # G1 = DEC Special Graphics
    parser.feed("\x1b*A")  # G2 = UK National
    parser.feed("\x1b+0")  # G3 = DEC Special Graphics
    parser.feed("\x0e")  # Switch to G1

    # Verify we're in G1 with graphics
    parser.feed("l")
    assert terminal.current_buffer.get_cell(0, 0)[1] == "┌"

    # Reset terminal
    parser.feed("\x1bc")  # ESC c (RIS - Reset)

    # Character sets should be reset to defaults
    assert terminal.g0_charset == "B"
    assert terminal.g1_charset == "B"
    assert terminal.g2_charset == "B"
    assert terminal.g3_charset == "B"
    assert terminal.current_charset == 0


def test_all_dec_special_graphics_characters():
    """Test the full DEC Special Graphics character set mapping."""
    terminal = Terminal(width=50, height=10)
    parser = Parser(terminal)

    parser.feed("\x1b(0")  # Set G0 to DEC Special Graphics

    # Test all the mapped characters
    test_chars = "jklmnqtuvwxa`fg~ops0_{}|"
    expected = "┘┐┌└┼─├┤┴┬│▒◆°±·⎺⎻⎽█ π£≠"

    parser.feed(test_chars)

    result = terminal.current_buffer.get_line_text(0)
    assert result[: len(expected)] == expected


def test_uk_national_character_set():
    """Test UK National character set (# -> £)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    parser.feed("\x1b(A")  # Set G0 to UK National

    parser.feed("Price: #10")

    assert terminal.current_buffer.get_line_text(0) == "Price: £10          "

    # Other characters should be unchanged
    parser.feed("\r\n")
    parser.feed("ABC!@$%^&*()")

    assert terminal.current_buffer.get_line_text(1) == "ABC!@$%^&*()        "
