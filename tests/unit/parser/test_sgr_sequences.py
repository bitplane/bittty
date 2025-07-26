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
from bittty.style import _parse_ansi_to_tuple, _tuple_to_ansi, merge_ansi_styles


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
    assert terminal.current_ansi_code == "\x1b[0m"


def test_sgr_bold_and_not_bold():
    """Test SGR 1 (Bold) and SGR 22 (Not bold)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_BOLD}m")
    assert terminal.current_ansi_code == "\x1b[1m"
    parser.feed(f"{ESC}[{SGR_NOT_BOLD_NOR_FAINT}m")
    assert terminal.current_ansi_code == "\x1b[22m"


def test_sgr_italic_and_not_italic():
    """Test SGR 3 (Italic) and SGR 23 (Not italic)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_ITALIC}m")
    assert terminal.current_ansi_code == "\x1b[3m"
    parser.feed(f"{ESC}[{SGR_NOT_ITALIC}m")
    assert terminal.current_ansi_code == "\x1b[23m"


def test_sgr_underline_and_not_underline():
    """Test SGR 4 (Underline) and SGR 24 (Not underlined)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_UNDERLINE}m")
    assert terminal.current_ansi_code == "\x1b[4m"
    parser.feed(f"{ESC}[{SGR_NOT_UNDERLINED}m")
    assert terminal.current_ansi_code == "\x1b[24m"


def test_sgr_blink_and_not_blink():
    """Test SGR 5 (Blink) and SGR 25 (Not blinking)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_BLINK}m")
    assert terminal.current_ansi_code == "\x1b[5m"
    parser.feed(f"{ESC}[{SGR_NOT_BLINKING}m")
    assert terminal.current_ansi_code == "\x1b[25m"


def test_sgr_reverse_and_not_reverse():
    """Test SGR 7 (Reverse) and SGR 27 (Not reversed)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_REVERSE}m")
    assert terminal.current_ansi_code == "\x1b[7m"
    parser.feed(f"{ESC}[{SGR_NOT_REVERSED}m")
    assert terminal.current_ansi_code == "\x1b[27m"


def test_sgr_conceal_and_not_conceal():
    """Test SGR 8 (Conceal) and SGR 28 (Not concealed)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_CONCEAL}m")
    assert terminal.current_ansi_code == "\x1b[8m"
    parser.feed(f"{ESC}[{SGR_NOT_CONCEALED}m")
    assert terminal.current_ansi_code == "\x1b[28m"


def test_sgr_strikethrough_and_not_strikethrough():
    """Test SGR 9 (Strikethrough) and SGR 29 (Not strikethrough)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[{SGR_STRIKE}m")
    assert terminal.current_ansi_code == "\x1b[9m"
    parser.feed(f"{ESC}[{SGR_NOT_STRIKETHROUGH}m")
    assert terminal.current_ansi_code == "\x1b[29m"


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
    assert terminal.current_ansi_code == "\x1b[0m"


def test_sgr_empty_background_extract():
    """Test extraction of empty background."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[0m")
    assert terminal.current_ansi_code == "\x1b[0m"


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
    assert terminal.current_ansi_code == "\x1b[39m"


def test_sgr_default_background_color():
    """Test SGR 49 (Default background color)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[49m")
    assert terminal.current_ansi_code == "\x1b[49m"


def test_sgr_malformed_rgb_foreground():
    """Test SGR with malformed RGB foreground sequence (missing values)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[38;2;100m")
    assert terminal.current_ansi_code == "\x1b[38;2;100m"


def test_sgr_malformed_rgb_background():
    """Test SGR with malformed RGB background sequence (missing values)."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[48;2;100m")
    assert terminal.current_ansi_code == "\x1b[48;2;100m"


def test_sgr_multiple_attributes():
    """Test combining multiple SGR attributes in one sequence."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[1;31;44m")  # Bold, red foreground, blue background
    assert terminal.current_ansi_code == "\x1b[1;31;44m" # Sorted: 1;31;44


def test_sgr_reset_and_then_set():
    """Test resetting attributes and then setting a new one."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[1;31m")  # Bold and red
    parser.feed(f"{ESC}[0m")  # Reset
    assert terminal.current_ansi_code == "\x1b[0m"
    parser.feed(f"{ESC}[32m")  # Green
    assert terminal.current_ansi_code == "\x1b[32m"


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
    assert terminal.current_ansi_code == "\x1b[0m"


def test_sgr_empty_background_extract():
    """Test extraction of empty background."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[0m")
    assert terminal.current_ansi_code == "\x1b[0m"


def test_sgr_single_off_attribute():
    """Test SGR with a single 'off' attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[22m") # Not bold
    assert terminal.current_ansi_code == "\x1b[22m"


def test_sgr_merge_none_with_true():
    """Test merging a style with None attribute with a style with True attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[1m") # Bold
    assert terminal.current_ansi_code == "\x1b[1m"
    parser.feed(f"{ESC}[32m") # Green
    assert terminal.current_ansi_code == "\x1b[1;32m"


def test_sgr_merge_true_with_false():
    """Test merging a style with True attribute with a style with False attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[1m") # Bold
    assert terminal.current_ansi_code == "\x1b[1m"
    parser.feed(f"{ESC}[22m") # Not bold
    assert terminal.current_ansi_code == "\x1b[22m"


def test_sgr_merge_false_with_true():
    """Test merging a style with False attribute with a style with True attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[22m") # Not bold
    assert terminal.current_ansi_code == "\x1b[22m"
    parser.feed(f"{ESC}[1m") # Bold
    assert terminal.current_ansi_code == "\x1b[1m"


def test_sgr_merge_none_with_false():
    """Test merging a style with None attribute with a style with False attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[32m") # Green
    assert terminal.current_ansi_code == "\x1b[32m"
    parser.feed(f"{ESC}[22m") # Not bold
    assert terminal.current_ansi_code == "\x1b[22;32m"


def test_sgr_merge_false_with_none():
    """Test merging a style with False attribute with a style with None attribute."""
    terminal = Terminal()
    parser = Parser(terminal)
    parser.feed(f"{ESC}[22m") # Not bold
    assert terminal.current_ansi_code == "\x1b[22m"
    parser.feed(f"{ESC}[32m") # Green
    assert terminal.current_ansi_code == "\x1b[22;32m"


def test_sgr_merge_all_attributes():
    """Test merging all attributes, including resets."""
    terminal = Terminal()
    parser = Parser(terminal)

    # Initial style: Bold, Red, Underline
    parser.feed(f"{ESC}[1;31;4m")
    assert terminal.current_ansi_code == "\x1b[1;31;4m"

    # New style: Not Bold, Blue background, Italic
    parser.feed(f"{ESC}[22;44;3m")
    assert terminal.current_ansi_code == "\x1b[22;24;3;32;44m"

    # Reset all, then set Green
    parser.feed(f"{ESC}[0m")
    assert terminal.current_ansi_code == "\x1b[0m"
    parser.feed(f"{ESC}[32m")
    assert terminal.current_ansi_code == "\x1b[32m"


def test_sgr_merge_complex_scenario():
    """Test a more complex merging scenario."""
    terminal = Terminal()
    parser = Parser(terminal)

    # Initial: Bold, Red FG, Blue BG, Underline
    parser.feed(f"{ESC}[1;31;44;4m")
    assert terminal.current_ansi_code == "\x1b[1;31;44;4m"

    # Apply: Not Bold, Green FG, Not Underline, Italic
    parser.feed(f"{ESC}[22;32;24;3m")
    assert terminal.current_ansi_code == "\x1b[22;24;3;32;44m"

    # Apply: Reset, then Blink, Cyan BG
    parser.feed(f"{ESC}[0m")
    assert terminal.current_ansi_code == "\x1b[0m"
    parser.feed(f"{ESC}[5;46m")
    assert terminal.current_ansi_code == "\x1b[5;46m"
