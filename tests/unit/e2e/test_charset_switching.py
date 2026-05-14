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

    assert terminal.current_buffer.get_line_text(0).rstrip() == "ABC┌─┐DEF"


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

    assert terminal.current_buffer.get_line_text(0).rstrip() == "A┌B"


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

    assert terminal.current_buffer.get_line_text(0).rstrip() == "A£B"


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

    assert terminal.current_buffer.get_line_text(0).rstrip() == "A┌£┐B"


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

    assert terminal.current_buffer.get_line_text(0).rstrip() == "A┌─┐B└┘─C"


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

    assert terminal.current_buffer.get_line_text(0).rstrip() == "┌──┐"
    assert terminal.current_buffer.get_line_text(1).rstrip() == "│  │"
    assert terminal.current_buffer.get_line_text(2).rstrip() == "└──┘"


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

    assert terminal.current_buffer.get_line_text(0).rstrip() == "Text┌─ £ ┐┘ End"


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
    assert terminal.current_buffer.get_line_text(0).rstrip() == "┌──┐TEXT"

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

    assert terminal.current_buffer.get_line_text(0).rstrip() == "Price: £10"

    # Other characters should be unchanged
    parser.feed("\r\n")
    parser.feed("ABC!@$%^&*()")

    assert terminal.current_buffer.get_line_text(1).rstrip() == "ABC!@$%^&*()"


def test_dec_technical_charset_designation():
    """Test DEC Technical character set designation and usage."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G1 to DEC Technical character set
    parser.feed("\x1b)>")  # ESC ) >

    # Verify charset was set
    assert terminal.g1_charset == ">"

    # Normal ASCII text
    parser.feed("Math: ")

    # Switch to G1 (DEC Technical)
    parser.feed("\x0e")  # SO (shift out to G1)

    # Type some mathematical symbols
    parser.feed("P")  # Should be Π (pi)
    parser.feed("S")  # Should be Σ (sigma)
    parser.feed("?")  # Should be ∫ (integral)

    # Switch back to G0
    parser.feed("\x0f")  # SI (shift in to G0)
    parser.feed("!")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "Math: ΠΣ∫!"


def test_dec_technical_greek_letters():
    """Test DEC Technical character set Greek letters."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G1 to DEC Technical
    parser.feed("\x1b)>")  # ESC ) >
    parser.feed("\x0e")  # Switch to G1

    # Test some Greek letters
    parser.feed("D")  # Δ (delta)
    parser.feed("F")  # Φ (phi)
    parser.feed("G")  # Γ (gamma)
    parser.feed("a")  # α (alpha)
    parser.feed("b")  # β (beta)
    parser.feed("p")  # π (pi)

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "ΔΦΓαβπ"


def test_dec_technical_mathematical_symbols():
    """Test DEC Technical character set mathematical symbols."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G1 to DEC Technical
    parser.feed("\x1b)>")  # ESC ) >
    parser.feed("\x0e")  # Switch to G1

    # Test mathematical operators
    parser.feed("B")  # ∞ (infinity)
    parser.feed("C")  # ÷ (division)
    parser.feed("K")  # × (multiplication)
    parser.feed("V")  # √ (square root)
    parser.feed("<")  # ≤ (less than or equal)
    parser.feed(">")  # ≥ (greater than or equal)

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "∞÷×√≤≥"


def test_german_national_charset():
    """Test German National character set (ESC ( K)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to German National
    parser.feed("\x1b(K")  # ESC ( K

    # Test German characters
    parser.feed("@[\\]`{|}")  # @ÄÖÜäöüß

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "§ÄÖÜäöüß"


def test_french_national_charset():
    """Test French National character set (ESC ( R)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to French National
    parser.feed("\x1b(R")  # ESC ( R

    # Test French characters: #@[\]`{|}~
    parser.feed("#@[\\]`{|}~")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "£à°ç§`éùè¨"


def test_spanish_national_charset():
    """Test Spanish National character set (ESC ( Z)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to Spanish National
    parser.feed("\x1b(Z")  # ESC ( Z

    # Test Spanish characters: #@[\]`{|
    parser.feed("#@[\\]`{|")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "£§¡Ñ¿˚ñç"


def test_italian_national_charset():
    """Test Italian National character set (ESC ( Y)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to Italian National
    parser.feed("\x1b(Y")  # ESC ( Y

    # Test Italian characters: #@[\]`{|}~
    parser.feed("#@[\\]`{|}~")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "£§°çéùàòèì"


def test_swedish_national_charset():
    """Test Swedish National character set (ESC ( H)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to Swedish National
    parser.feed("\x1b(H")  # ESC ( H

    # Test Swedish characters: @[\]^`{|}~
    parser.feed("@[\\]^`{|}~")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "ÉÄÖÅÜéäöåü"


def test_danish_norwegian_charset():
    """Test Danish/Norwegian National character set (ESC ( E)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to Danish/Norwegian National
    parser.feed("\x1b(E")  # ESC ( E

    # Test Danish/Norwegian characters: [\]`{|
    parser.feed("[\\]`{|")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "ÆØÅæøå"


def test_finnish_national_charset():
    """Test Finnish National character set (ESC ( C)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to Finnish National
    parser.feed("\x1b(C")  # ESC ( C

    # Test Finnish characters: [\]^`{|}~
    parser.feed("[\\]^`{|}~")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "ÄÖÅÜéäöåü"


def test_dutch_national_charset():
    """Test Dutch National character set (ESC ( 4)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to Dutch National
    parser.feed("\x1b(4")  # ESC ( 4

    # Test Dutch characters: #@[\]`{|}~
    parser.feed("#@[\\]`{|}~")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "£¾ĳ½¦`¨ƒ¼´"


def test_french_canadian_charset():
    """Test French Canadian National character set (ESC ( Q)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to French Canadian National
    parser.feed("\x1b(Q")  # ESC ( Q

    # Test French Canadian characters: @[\]^`{|}~
    parser.feed("@[\\]^`{|}~")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "àâçêîôéùèû"


def test_japanese_roman_charset():
    """Test Japanese Roman character set (ESC ( J)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to Japanese Roman
    parser.feed("\x1b(J")  # ESC ( J

    # Test Japanese Roman characters: \~
    parser.feed("Price: \\100~")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "Price: ¥100¯"


def test_swiss_national_charset():
    """Test Swiss National character set (ESC ( =)."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set G0 to Swiss National
    parser.feed("\x1b(=")  # ESC ( =

    # Test Swiss characters: #@[\]^_`{|}~
    parser.feed("#@[\\]^_`{|}~")

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "ùàéçêîèôäöüû"


def test_national_charset_switching():
    """Test switching between different national character sets."""
    terminal = Terminal(width=30, height=5)
    parser = Parser(terminal)

    # Set G0 to German, G1 to French
    parser.feed("\x1b(K")  # German G0
    parser.feed("\x1b)R")  # French G1

    # Type German characters in G0
    parser.feed("@[")  # German: §Ä

    # Switch to G1 (French)
    parser.feed("\x0e")  # SO
    parser.feed("@[")  # French: à°

    # Switch back to G0 (German)
    parser.feed("\x0f")  # SI
    parser.feed("]")  # German: Ü

    # Check the result
    assert terminal.current_buffer.get_line_text(0).rstrip() == "§Äà°Ü"
