"""
Test cases for the terminal color handling module.
"""

from bittty import color as color_module


# --- Tests for get_color_code() ---


def test_get_color_code_foreground_only():
    """get_color_code should generate correct ANSI for foreground color."""
    result = color_module.get_color_code(fg=1)
    assert result == "\033[38;5;1m"


def test_get_color_code_background_only():
    """get_color_code should generate correct ANSI for background color."""
    result = color_module.get_color_code(bg=2)
    assert result == "\033[48;5;2m"


def test_get_color_code_both_colors():
    """get_color_code should generate correct ANSI for both colors."""
    result = color_module.get_color_code(fg=1, bg=2)
    assert result == "\033[38;5;1;48;5;2m"


def test_get_color_code_no_colors():
    """get_color_code should return empty string when no colors specified."""
    result = color_module.get_color_code()
    assert result == ""


# --- Tests for get_rgb_code() ---


def test_get_rgb_code_foreground_only():
    """get_rgb_code should generate correct ANSI for RGB foreground."""
    result = color_module.get_rgb_code(fg_rgb=(255, 0, 0))
    assert result == "\033[38;2;255;0;0m"


def test_get_rgb_code_background_only():
    """get_rgb_code should generate correct ANSI for RGB background."""
    result = color_module.get_rgb_code(bg_rgb=(0, 255, 0))
    assert result == "\033[48;2;0;255;0m"


def test_get_rgb_code_both_colors():
    """get_rgb_code should generate correct ANSI for both RGB colors."""
    result = color_module.get_rgb_code(fg_rgb=(255, 0, 0), bg_rgb=(0, 255, 0))
    assert result == "\033[38;2;255;0;0;48;2;0;255;0m"


def test_get_rgb_code_no_colors():
    """get_rgb_code should return empty string when no colors specified."""
    result = color_module.get_rgb_code()
    assert result == ""


# --- Tests for get_style_code() ---


def test_get_style_code_bold():
    """get_style_code should generate correct ANSI for bold."""
    result = color_module.get_style_code(bold=True)
    assert result == "\033[1m"


def test_get_style_code_multiple_styles():
    """get_style_code should generate correct ANSI for multiple styles."""
    result = color_module.get_style_code(bold=True, italic=True, underline=True)
    assert result == "\033[1;3;4m"


def test_get_style_code_all_styles():
    """get_style_code should handle all style attributes."""
    result = color_module.get_style_code(
        bold=True, dim=True, italic=True, underline=True, blink=True, reverse=True, conceal=True, strike=True
    )
    assert result == "\033[1;2;3;4;5;7;8;9m"


def test_get_style_code_no_styles():
    """get_style_code should return empty string when no styles specified."""
    result = color_module.get_style_code()
    assert result == ""


# --- Tests for get_combined_code() ---


def test_get_combined_code_color_and_style():
    """get_combined_code should combine colors and styles correctly."""
    result = color_module.get_combined_code(fg=1, bg=2, bold=True, italic=True)
    assert result == "\033[1;3;38;5;1;48;5;2m"


def test_get_combined_code_rgb_takes_precedence():
    """get_combined_code should use RGB colors over palette colors."""
    result = color_module.get_combined_code(fg=1, fg_rgb=(255, 0, 0), bg=2, bg_rgb=(0, 255, 0))
    assert result == "\033[38;2;255;0;0;48;2;0;255;0m"


def test_get_combined_code_styles_only():
    """get_combined_code should work with styles only."""
    result = color_module.get_combined_code(bold=True, underline=True)
    assert result == "\033[1;4m"


def test_get_combined_code_colors_only():
    """get_combined_code should work with colors only."""
    result = color_module.get_combined_code(fg=1, bg=2)
    assert result == "\033[38;5;1;48;5;2m"


def test_get_combined_code_empty():
    """get_combined_code should return empty string when nothing specified."""
    result = color_module.get_combined_code()
    assert result == ""


# --- Tests for get_basic_color_code() ---


def test_get_basic_color_code_normal_foreground():
    """get_basic_color_code should handle normal foreground colors (0-7)."""
    result = color_module.get_basic_color_code(1, is_bg=False)
    assert result == "\033[31m"


def test_get_basic_color_code_normal_background():
    """get_basic_color_code should handle normal background colors (0-7)."""
    result = color_module.get_basic_color_code(2, is_bg=True)
    assert result == "\033[42m"


def test_get_basic_color_code_bright_foreground():
    """get_basic_color_code should handle bright foreground colors (8-15)."""
    result = color_module.get_basic_color_code(9, is_bg=False)
    assert result == "\033[91m"


def test_get_basic_color_code_bright_background():
    """get_basic_color_code should handle bright background colors (8-15)."""
    result = color_module.get_basic_color_code(10, is_bg=True)
    assert result == "\033[102m"


def test_get_basic_color_code_out_of_range():
    """get_basic_color_code should return empty string for invalid colors."""
    assert color_module.get_basic_color_code(16) == ""
    assert color_module.get_basic_color_code(-1) == ""


# --- Tests for utility functions ---


def test_reset_code():
    """reset_code should return correct ANSI reset sequence."""
    result = color_module.reset_code()
    assert result == "\033[0m"


def test_get_cursor_code():
    """get_cursor_code should return correct ANSI cursor sequence."""
    result = color_module.get_cursor_code()
    assert result == "\033[7m"


def test_get_clear_line_code():
    """get_clear_line_code should return correct ANSI clear line sequence."""
    result = color_module.get_clear_line_code()
    assert result == "\033[K"


# --- Tests for LRU caching behavior ---


def test_functions_are_cached():
    """Functions should return the same object for same inputs (LRU cache)."""
    # Test that calling with same args returns cached result
    result1 = color_module.get_combined_code(fg=1, bold=True)
    result2 = color_module.get_combined_code(fg=1, bold=True)

    # They should be equal (same result)
    assert result1 == result2

    # For LRU cache, they should actually be the same object
    assert result1 is result2


def test_cache_different_inputs():
    """Different inputs should produce different cached results."""
    result1 = color_module.get_combined_code(fg=1, bold=True)
    result2 = color_module.get_combined_code(fg=2, bold=True)

    assert result1 != result2
    assert result1 == "\033[1;38;5;1m"
    assert result2 == "\033[1;38;5;2m"
