"""Tests for charset translation functionality in terminal."""

from bittty.terminal import Terminal
from bittty.parser import Parser


def test_translate_charset_default():
    """Test character translation with default charset."""
    terminal = Terminal(width=80, height=24)

    # Default charset should not translate
    result = terminal._translate_charset("hello")
    assert result == "hello"


def test_translate_charset_dec_special():
    """Test character translation with DEC Special Graphics."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Set G0 to DEC Special Graphics
    parser.feed("\x1b(0")  # ESC ( 0 sets G0 to DEC Special

    # Test translation of DEC special characters
    # 'q' should become horizontal line
    result = terminal._translate_charset("q")
    assert result == "─"  # DEC special graphics mapping


def test_single_shift_translation():
    """Test character translation with single shift (SS2/SS3)."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Set G2 to DEC Special Graphics
    parser.feed("\x1b*0")  # ESC * 0 sets G2 to DEC Special

    # Use single shift 2 for next character
    parser.feed("\x1bN")  # SS2 - use G2 for next char

    # Next character should use G2 charset
    result = terminal._translate_charset("q")
    assert result == "─"  # Should use DEC special from G2

    # Second character should use normal G0
    result = terminal._translate_charset("q")
    assert result == "q"  # Back to normal G0


def test_charset_switching():
    """Test switching between G0 and G1 charsets."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Set G1 to DEC Special Graphics
    parser.feed("\x1b)0")  # ESC ) 0 sets G1 to DEC Special

    # Switch to G1
    parser.feed("\x0e")  # SO - shift out to G1

    result = terminal._translate_charset("q")
    assert result == "─"  # Should use DEC special from G1

    # Switch back to G0
    parser.feed("\x0f")  # SI - shift in to G0

    result = terminal._translate_charset("q")
    assert result == "q"  # Back to normal G0


def test_multiple_charset_sets():
    """Test setting multiple charset designators."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Set different charsets for each G set
    parser.feed("\x1b(A")  # G0 = UK charset
    parser.feed("\x1b)0")  # G1 = DEC Special
    parser.feed("\x1b*B")  # G2 = US ASCII
    parser.feed("\x1b+0")  # G3 = DEC Special

    # Verify they're set correctly
    assert terminal.g0_charset == "A"
    assert terminal.g1_charset == "0"
    assert terminal.g2_charset == "B"
    assert terminal.g3_charset == "0"


def test_single_shift_reset():
    """Test that single shift resets after one character."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Set G2 to DEC Special
    parser.feed("\x1b*0")

    # Use SS2
    parser.feed("\x1bN")  # SS2

    # First character uses G2
    result1 = terminal._translate_charset("q")
    assert result1 == "─"

    # Single shift should be reset now
    assert terminal.single_shift is None

    # Second character uses normal G0
    result2 = terminal._translate_charset("q")
    assert result2 == "q"
