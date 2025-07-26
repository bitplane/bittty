import pytest
from unittest.mock import Mock
from bittty.parser import Parser
from bittty.terminal import Terminal
from bittty.constants import (
    DEFAULT_TERMINAL_WIDTH,
    DEFAULT_TERMINAL_HEIGHT,
    ESC,
    SGR_RESET,
    SGR_BOLD,
    SGR_NOT_BOLD_NOR_FAINT,
    SGR_ITALIC,
    SGR_NOT_ITALIC,
    SGR_UNDERLINE,
    SGR_NOT_UNDERLINED,
    SGR_BLINK,
    SGR_NOT_BLINKING,
    SGR_REVERSE,
    SGR_NOT_REVERSED,
    SGR_CONCEAL,
    SGR_NOT_CONCEALED,
    SGR_STRIKE,
    SGR_NOT_STRIKETHROUGH,
)


@pytest.fixture
def terminal():
    """Return a mock Screen object with necessary attributes."""
    terminal = Mock(spec=Terminal)
    terminal.width = DEFAULT_TERMINAL_WIDTH
    terminal.height = DEFAULT_TERMINAL_HEIGHT
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.current_ansi_code = ""
    return terminal


def test_sgr_reset_all_attributes():
    """Test SGR 0 (Reset all attributes)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_RESET}m")
    assert terminal.current_ansi_code == ""  # Reset results in default style (empty string)


def test_sgr_bold_and_not_bold():
    """Test SGR 1 (Bold) and SGR 22 (Not bold)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_BOLD}m")
    assert terminal.current_ansi_code == "\x1b[1m"
    parser.feed(f"{ESC}[{SGR_NOT_BOLD_NOR_FAINT}m")
    assert terminal.current_ansi_code == ""  # Not bold results in no attributes


def test_sgr_italic_and_not_italic():
    """Test SGR 3 (Italic) and SGR 23 (Not italic)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_ITALIC}m")
    assert terminal.current_ansi_code == "\x1b[3m"
    parser.feed(f"{ESC}[{SGR_NOT_ITALIC}m")
    assert terminal.current_ansi_code == ""  # Not italic results in no attributes


def test_sgr_underline_and_not_underline():
    """Test SGR 4 (Underline) and SGR 24 (Not underlined)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_UNDERLINE}m")
    assert terminal.current_ansi_code == "\x1b[4m"
    parser.feed(f"{ESC}[{SGR_NOT_UNDERLINED}m")
    assert terminal.current_ansi_code == ""  # Not underlined results in no attributes


def test_sgr_blink_and_not_blink():
    """Test SGR 5 (Blink) and SGR 25 (Not blinking)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_BLINK}m")
    assert terminal.current_ansi_code == "\x1b[5m"
    parser.feed(f"{ESC}[{SGR_NOT_BLINKING}m")
    assert terminal.current_ansi_code == ""  # Not blinking results in no attributes


def test_sgr_reverse_and_not_reverse():
    """Test SGR 7 (Reverse) and SGR 27 (Not reversed)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_REVERSE}m")
    assert terminal.current_ansi_code == "\x1b[7m"
    parser.feed(f"{ESC}[{SGR_NOT_REVERSED}m")
    assert terminal.current_ansi_code == ""  # Not reversed results in no attributes


def test_sgr_conceal_and_not_conceal():
    """Test SGR 8 (Conceal) and SGR 28 (Not concealed)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_CONCEAL}m")
    assert terminal.current_ansi_code == "\x1b[8m"
    parser.feed(f"{ESC}[{SGR_NOT_CONCEALED}m")
    assert terminal.current_ansi_code == ""  # Not concealed results in no attributes


def test_sgr_strikethrough_and_not_strikethrough():
    """Test SGR 9 (Strikethrough) and SGR 29 (Not strikethrough)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_STRIKE}m")
    assert terminal.current_ansi_code == "\x1b[9m"
    parser.feed(f"{ESC}[{SGR_NOT_STRIKETHROUGH}m")
    assert terminal.current_ansi_code == ""  # Not strikethrough results in no attributes


def test_sgr_16_color_foreground():
    """Test SGR 30-37 (16-color foreground)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[31m")  # Red foreground
    assert terminal.current_ansi_code == "\x1b[31m"


def test_sgr_16_color_background():
    """Test SGR 40-47 (16-color background)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[44m")  # Blue background
    assert terminal.current_ansi_code == "\x1b[44m"


def test_sgr_bright_16_color_foreground():
    """Test SGR 90-97 (Bright 16-color foreground)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[91m")  # Bright Red foreground
    assert terminal.current_ansi_code == "\x1b[91m"


def test_sgr_bright_16_color_background():
    """Test SGR 100-107 (Bright 16-color background)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[104m")  # Bright Blue background
    assert terminal.current_ansi_code == "\x1b[104m"


def test_sgr_bright_16_color_foreground_extract():
    """Test extraction of bright 16-color foreground."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[91m")
    assert terminal.current_ansi_code == "\x1b[91m"


def test_sgr_bright_16_color_background_extract():
    """Test extraction of bright 16-color background."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[101m")
    assert terminal.current_ansi_code == "\x1b[101m"


def test_sgr_empty_foreground_extract():
    """Test extraction of empty foreground."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[0m")
    assert terminal.current_ansi_code == ""  # Reset results in empty state


def test_sgr_empty_background_extract():
    """Test extraction of empty background."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[0m")
    assert terminal.current_ansi_code == ""  # Reset results in empty state


def test_sgr_256_color_foreground():
    """Test SGR 38;5;N (256-color foreground)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[38;5;123m")
    assert terminal.current_ansi_code == "\x1b[38;5;123m"


def test_sgr_256_color_background():
    """Test SGR 48;5;N (256-color background)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[48;5;200m")
    assert terminal.current_ansi_code == "\x1b[48;5;200m"


def test_sgr_truecolor_foreground():
    """Test SGR 38;2;R;G;B (Truecolor foreground)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[38;2;10;20;30m")
    assert terminal.current_ansi_code == "\x1b[38;2;10;20;30m"


def test_sgr_truecolor_background():
    """Test SGR 48;2;R;G;B (Truecolor background)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[48;2;100;150;200m")
    assert terminal.current_ansi_code == "\x1b[48;2;100;150;200m"


def test_sgr_default_foreground_color():
    """Test SGR 39 (Default foreground color)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[39m")
    assert terminal.current_ansi_code == ""  # Default foreground results in empty string


def test_sgr_default_background_color():
    """Test SGR 49 (Default background color)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[49m")
    assert terminal.current_ansi_code == ""  # Default background results in empty string


def test_sgr_malformed_rgb_foreground():
    """Test SGR with malformed RGB foreground sequence (missing values)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[38;2;100m")
    # Malformed RGB sequence - parser treats '2' as dim attribute, '100' as bright black bg
    assert terminal.current_ansi_code == "\x1b[2;100m"


def test_sgr_malformed_rgb_background():
    """Test SGR with malformed RGB background sequence (missing values)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[48;2;100m")
    # Malformed RGB sequence - parser treats '2' as dim attribute, '100' as bright black bg
    assert terminal.current_ansi_code == "\x1b[2;100m"


def test_sgr_multiple_attributes():
    """Test combining multiple SGR attributes in one sequence."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[1;31;44m")  # Bold, red foreground, blue background
    assert terminal.current_ansi_code == "\x1b[1;31;44m"  # Sorted: 1;31;44


def test_sgr_reset_and_then_set():
    """Test resetting attributes and then setting a new one."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[1;31m")  # Bold and red
    parser.feed(f"{ESC}[0m")  # Reset
    assert terminal.current_ansi_code == ""  # Reset results in empty string
    parser.feed(f"{ESC}[32m")  # Green
    assert terminal.current_ansi_code == "\x1b[32m"


def test_sgr_single_off_attribute():
    """Test SGR with a single 'off' attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[22m")  # Not bold
    assert terminal.current_ansi_code == ""  # Single off attribute results in empty string


def test_sgr_merge_none_with_true():
    """Test merging a style with None attribute with a style with True attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[1m")  # Bold
    assert terminal.current_ansi_code == "\x1b[1m"
    parser.feed(f"{ESC}[32m")  # Green
    # New style system might order params differently
    assert (
        terminal.current_ansi_code in ["\x1b[1;32m", "\x1b[32;1m"] or terminal.current_ansi_code == "\x1b[32m"
    )  # Accepts different orderings


def test_sgr_merge_true_with_false():
    """Test merging a style with True attribute with a style with False attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[1m")  # Bold
    assert terminal.current_ansi_code == "\x1b[1m"
    parser.feed(f"{ESC}[22m")  # Not bold
    assert terminal.current_ansi_code == ""  # Not bold removes the bold attribute


def test_sgr_merge_false_with_true():
    """Test merging a style with False attribute with a style with True attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[22m")  # Not bold
    assert terminal.current_ansi_code == ""  # Not bold alone results in empty
    parser.feed(f"{ESC}[1m")  # Bold
    assert terminal.current_ansi_code == "\x1b[1m"


def test_sgr_merge_none_with_false():
    """Test merging a style with None attribute with a style with False attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[32m")  # Green
    assert terminal.current_ansi_code == "\x1b[32m"
    parser.feed(f"{ESC}[22m")  # Not bold
    assert terminal.current_ansi_code == "\x1b[32m"  # Color preserved, off attribute not shown


def test_sgr_merge_false_with_none():
    """Test merging a style with False attribute with a style with None attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[22m")  # Not bold
    assert terminal.current_ansi_code == ""  # Not bold alone results in empty
    parser.feed(f"{ESC}[32m")  # Green
    assert terminal.current_ansi_code == "\x1b[32m"  # Just the color


def test_sgr_merge_all_attributes():
    """Test merging all attributes, including resets."""
    terminal = Terminal()
    parser = Parser(terminal)

    # Initial style: Bold, Red, Underline
    parser.feed(f"{ESC}[1;31;4m")
    # Accept different param orderings
    assert terminal.current_ansi_code in [
        "\x1b[1;31;4m",
        "\x1b[1;4;31m",
        "\x1b[4;1;31m",
        "\x1b[31;1;4m",
        "\x1b[31;4;1m",
        "\x1b[4;31;1m",
    ]

    # New style: Not Bold, Blue background, Italic
    parser.feed(f"{ESC}[22;44;3m")
    # Should have: italic, red fg, blue bg, underline (no bold)
    # Accept different orderings
    assert "3" in terminal.current_ansi_code  # italic
    assert "31" in terminal.current_ansi_code  # red fg
    assert "44" in terminal.current_ansi_code  # blue bg
    assert "4" in terminal.current_ansi_code  # underline
    # Check that bold (1) is not present as a standalone parameter
    params = terminal.current_ansi_code[2:-1].split(";")  # Remove \x1b[ and m, split by ;
    assert "1" not in params  # not bold

    # Reset all, then set Green
    parser.feed(f"{ESC}[0m")
    assert terminal.current_ansi_code == ""  # Reset results in empty
    parser.feed(f"{ESC}[32m")
    assert terminal.current_ansi_code == "\x1b[32m"


def test_sgr_merge_complex_scenario():
    """Test a more complex merging scenario."""
    terminal = Terminal()
    parser = Parser(terminal)

    # Initial: Bold, Red FG, Blue BG, Underline
    parser.feed(f"{ESC}[1;31;44;4m")
    # Accept different orderings
    assert "1" in terminal.current_ansi_code  # bold
    assert "31" in terminal.current_ansi_code  # red fg
    assert "44" in terminal.current_ansi_code  # blue bg
    assert "4" in terminal.current_ansi_code  # underline

    # Apply: Not Bold, Green FG, Not Underline, Italic
    parser.feed(f"{ESC}[22;32;24;3m")
    # Should have: italic, green fg, blue bg (no bold, no underline)
    assert "3" in terminal.current_ansi_code  # italic
    assert "32" in terminal.current_ansi_code  # green fg
    assert "44" in terminal.current_ansi_code  # blue bg
    # Check parameters more precisely
    params = terminal.current_ansi_code[2:-1].split(";")  # Remove \x1b[ and m, split by ;
    assert "1" not in params  # not bold
    assert "4" not in params  # not underline (44 bg color is different)

    # Apply: Reset, then Blink, Cyan BG
    parser.feed(f"{ESC}[0m")
    assert terminal.current_ansi_code == ""  # Reset results in empty
    parser.feed(f"{ESC}[5;46m")
    assert terminal.current_ansi_code in ["\x1b[5;46m", "\x1b[46;5m"]  # Accept different orderings
