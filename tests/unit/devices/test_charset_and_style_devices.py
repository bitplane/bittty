from bittty.operations import Operation
from bittty.style import Color, Style, parse_sgr_sequence
from bittty.terminal import Terminal
from bittty.parser import Parser


def test_charset_device_translates_active_and_single_shift_charsets():
    terminal = Terminal(width=10, height=3)
    charset = terminal.board.charset

    charset.set_g0_charset("0")
    assert charset.translate("q") == "─"

    charset.set_g2_charset("0")
    charset.set_g0_charset("B")
    charset.single_shift_2()
    assert charset.translate("qz") == "─z"
    assert charset.single_shift is None


def test_charset_device_handles_operations_and_reset():
    terminal = Terminal(width=10, height=3)
    charset = terminal.board.charset

    charset.handle_charset_operation(Operation("charset", "SCS_G1", ("0",), "\x1b)0"))
    charset.handle_escape_operation(Operation("escape", "SS3", raw="\x1bO"))

    assert charset.g1_charset == "0"
    assert charset.single_shift == 3

    charset.reset()
    assert [charset.g0_charset, charset.g1_charset, charset.g2_charset, charset.g3_charset] == ["B", "B", "B", "B"]
    assert charset.current_charset == 0
    assert charset.single_shift is None


def test_style_device_applies_reset_and_merge():
    terminal = Terminal(width=10, height=3)
    style = terminal.board.style

    style.apply_sgr(Style(bold=True))
    style.apply_sgr(Style(fg=Color("indexed", 1)))

    parsed = parse_sgr_sequence(style.current_ansi_code)
    assert parsed.bold is True
    assert parsed.fg == Color("indexed", 1)

    style.apply_sgr(Style(), reset=True)
    assert style.current_ansi_code == ""


def test_style_device_reports_background_ansi():
    terminal = Terminal(width=10, height=3)

    terminal.board.style.current_ansi_code = "\x1b[48;5;21m"

    assert terminal.board.style.background_ansi() == "\x1b[48;5;21m"


"""Tests for charset translation functionality in terminal."""


def test_translate_charset_default():
    """Test character translation with default charset."""
    terminal = Terminal(width=80, height=24)

    # Default charset should not translate
    result = terminal.board.charset.translate("hello")
    assert result == "hello"


def test_translate_charset_dec_special():
    """Test character translation with DEC Special Graphics."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal.board)

    # Set G0 to DEC Special Graphics
    parser.feed("\x1b(0")  # ESC ( 0 sets G0 to DEC Special

    # Test translation of DEC special characters
    # 'q' should become horizontal line
    result = terminal.board.charset.translate("q")
    assert result == "─"  # DEC special graphics mapping


def test_single_shift_translation():
    """Test character translation with single shift (SS2/SS3)."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal.board)

    # Set G2 to DEC Special Graphics
    parser.feed("\x1b*0")  # ESC * 0 sets G2 to DEC Special

    # Use single shift 2 for next character
    parser.feed("\x1bN")  # SS2 - use G2 for next char

    # Next character should use G2 charset
    result = terminal.board.charset.translate("q")
    assert result == "─"  # Should use DEC special from G2

    # Second character should use normal G0
    result = terminal.board.charset.translate("q")
    assert result == "q"  # Back to normal G0


def test_charset_switching():
    """Test switching between G0 and G1 charsets."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal.board)

    # Set G1 to DEC Special Graphics
    parser.feed("\x1b)0")  # ESC ) 0 sets G1 to DEC Special

    # Switch to G1
    parser.feed("\x0e")  # SO - shift out to G1

    result = terminal.board.charset.translate("q")
    assert result == "─"  # Should use DEC special from G1

    # Switch back to G0
    parser.feed("\x0f")  # SI - shift in to G0

    result = terminal.board.charset.translate("q")
    assert result == "q"  # Back to normal G0


def test_multiple_charset_sets():
    """Test setting multiple charset designators."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal.board)

    # Set different charsets for each G set
    parser.feed("\x1b(A")  # G0 = UK charset
    parser.feed("\x1b)0")  # G1 = DEC Special
    parser.feed("\x1b*B")  # G2 = US ASCII
    parser.feed("\x1b+0")  # G3 = DEC Special

    # Verify they're set correctly
    assert terminal.board.charset.g0_charset == "A"
    assert terminal.board.charset.g1_charset == "0"
    assert terminal.board.charset.g2_charset == "B"
    assert terminal.board.charset.g3_charset == "0"


def test_single_shift_reset():
    """Test that single shift resets after one character."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal.board)

    # Set G2 to DEC Special
    parser.feed("\x1b*0")

    # Use SS2
    parser.feed("\x1bN")  # SS2

    # First character uses G2
    result1 = terminal.board.charset.translate("q")
    assert result1 == "─"

    # Single shift should be reset now
    assert terminal.board.charset.single_shift is None

    # Second character uses normal G0
    result2 = terminal.board.charset.translate("q")
    assert result2 == "q"
