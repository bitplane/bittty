"""Tests for Style.diff method and color functionality."""

from bittty.style import Style, Color, get_background


def test_diff_identical_styles_returns_empty():
    """Test that identical styles return empty string."""
    style1 = Style(fg=Color("rgb", (255, 0, 0)), bold=True)
    style2 = Style(fg=Color("rgb", (255, 0, 0)), bold=True)

    assert style1.diff(style2) == ""


def test_diff_to_default_returns_reset():
    """Test that transitioning to default style returns reset."""
    colored_style = Style(fg=Color("rgb", (255, 0, 0)), bold=True)
    default_style = Style()

    assert colored_style.diff(default_style) == "\x1b[0m"


def test_diff_from_default_returns_full_style():
    """Test that transitioning from default style returns full ANSI."""
    default_style = Style()
    colored_style = Style(fg=Color("rgb", (255, 0, 0)), bold=True)

    result = default_style.diff(colored_style)
    # Should contain both red color and bold
    assert "38;2;255;0;0" in result
    assert "1" in result
    assert result.startswith("\x1b[")
    assert result.endswith("m")


def test_diff_complex_transition_uses_reset():
    """Test that complex transitions use reset+target for now."""
    style1 = Style(fg=Color("indexed", 1), bg=Color("indexed", 2), bold=True)
    style2 = Style(fg=Color("rgb", (255, 0, 0)), italic=True)

    result = style1.diff(style2)
    # Should start with reset
    assert result.startswith("\x1b[0m")
    # Should contain the target style
    assert "38;2;255;0;0" in result
    assert "3" in result  # italic


def test_diff_only_foreground_change():
    """Test transition with only foreground color change."""
    style1 = Style(fg=Color("indexed", 1), bold=True)
    style2 = Style(fg=Color("indexed", 2), bold=True)

    result = style1.diff(style2)
    # For now, should use reset approach
    assert "\x1b[0m" in result
    assert "32" in result  # red foreground (indexed 2)
    assert "1" in result  # bold


def test_diff_only_background_change():
    """Test transition with only background color change."""
    style1 = Style(bg=Color("indexed", 1), bold=True)
    style2 = Style(bg=Color("indexed", 2), bold=True)

    result = style1.diff(style2)
    assert "\x1b[0m" in result
    assert "42" in result  # green background (indexed 2)
    assert "1" in result  # bold


def test_diff_rgb_colors():
    """Test transitions with RGB colors."""
    style1 = Style(fg=Color("rgb", (255, 0, 0)))
    style2 = Style(fg=Color("rgb", (0, 255, 0)))

    result = style1.diff(style2)
    assert "38;2;0;255;0" in result


def test_diff_indexed_to_rgb():
    """Test transition from indexed to RGB color."""
    style1 = Style(fg=Color("indexed", 1))
    style2 = Style(fg=Color("rgb", (128, 64, 32)))

    result = style1.diff(style2)
    assert "38;2;128;64;32" in result


def test_diff_attribute_changes():
    """Test transitions with attribute changes."""
    style1 = Style(bold=True, italic=False)
    style2 = Style(bold=False, italic=True)

    result = style1.diff(style2)
    assert "\x1b[0m" in result
    assert "3" in result  # italic


def test_diff_add_attributes():
    """Test adding attributes to existing style."""
    style1 = Style(bold=True)
    style2 = Style(bold=True, italic=True, underline=True)

    result = style1.diff(style2)
    # Should include all target attributes
    assert "1" in result  # bold
    assert "3" in result  # italic
    assert "4" in result  # underline


def test_diff_remove_attributes():
    """Test removing attributes from existing style."""
    style1 = Style(bold=True, italic=True, underline=True)
    style2 = Style(italic=True)

    result = style1.diff(style2)
    # Should use reset approach and only include italic
    assert "\x1b[0m" in result
    assert "3" in result  # italic
    # Should not contain bold or underline in final state


def test_diff_mixed_color_and_attributes():
    """Test complex transitions with both colors and attributes."""
    style1 = Style(fg=Color("indexed", 1), bg=Color("rgb", (100, 100, 100)), bold=True, italic=False)
    style2 = Style(fg=Color("rgb", (255, 255, 0)), bg=Color("indexed", 4), bold=False, italic=True)

    result = style1.diff(style2)
    assert "\x1b[0m" in result
    assert "38;2;255;255;0" in result  # yellow fg
    assert "44" in result  # blue bg
    assert "3" in result  # italic


def test_diff_caching_works():
    """Test that diff results are cached for performance."""
    style1 = Style(fg=Color("rgb", (255, 0, 0)))
    style2 = Style(fg=Color("rgb", (0, 255, 0)))

    # Call diff multiple times
    result1 = style1.diff(style2)
    result2 = style1.diff(style2)
    result3 = style1.diff(style2)

    # Results should be identical (and cached)
    assert result1 == result2 == result3

    # Cache info should show hits
    cache_info = style1.diff.cache_info()
    assert cache_info.hits >= 2


def test_diff_default_to_default_returns_empty():
    """Test that default to default transition returns empty."""
    default1 = Style()
    default2 = Style()

    assert default1.diff(default2) == ""


def test_diff_preserves_style_objects():
    """Test that diff doesn't modify the original style objects."""
    original_style1 = Style(fg=Color("rgb", (255, 0, 0)), bold=True)
    original_style2 = Style(fg=Color("rgb", (0, 255, 0)), italic=True)

    # Store original state
    style1_fg_before = original_style1.fg
    style1_bold_before = original_style1.bold
    style2_fg_before = original_style2.fg
    style2_italic_before = original_style2.italic

    # Call diff
    original_style1.diff(original_style2)

    # Verify objects are unchanged
    assert original_style1.fg == style1_fg_before
    assert original_style1.bold == style1_bold_before
    assert original_style2.fg == style2_fg_before
    assert original_style2.italic == style2_italic_before


def test_default_color_ansi():
    """Test default color returns empty string."""
    color = Color("default")
    assert color.ansi == ""


def test_indexed_color_ansi():
    """Test indexed color returns proper format."""
    color = Color("indexed", 5)
    assert color.ansi == "5;5"


def test_rgb_color_ansi():
    """Test RGB color returns proper format."""
    color = Color("rgb", (255, 128, 64))
    assert color.ansi == "2;255;128;64"


def test_invalid_mode_returns_empty():
    """Test invalid color mode returns empty string."""
    # This hits the fallback return "" in Color.ansi
    color = Color("invalid_mode")
    assert color.ansi == ""


def test_get_background_default():
    """Test get_background with default background."""
    ansi = "\x1b[31m"  # Only foreground red
    result = get_background(ansi)
    assert result == ""


def test_get_background_indexed_low():
    """Test get_background with low indexed background (0-7)."""
    ansi = "\x1b[41m"  # Red background (index 1)
    result = get_background(ansi)
    assert result == "\x1b[41m"


def test_get_background_indexed_high():
    """Test get_background with high indexed background (8-15)."""
    ansi = "\x1b[101m"  # Bright red background (index 9)
    result = get_background(ansi)
    assert result == "\x1b[101m"


def test_get_background_indexed_256():
    """Test get_background with 256-color indexed background."""
    ansi = "\x1b[48;5;196m"  # 256-color red background
    result = get_background(ansi)
    assert result == "\x1b[48;5;196m"


def test_get_background_rgb():
    """Test get_background with RGB background."""
    ansi = "\x1b[48;2;255;128;64m"  # RGB background
    result = get_background(ansi)
    assert result == "\x1b[48;2;255;128;64m"


def test_color_str():
    """Test Color.__str__ method."""
    color1 = Color("indexed", 5)
    assert str(color1) == "5;5"

    color2 = Color("rgb", (255, 0, 0))
    assert str(color2) == "2;255;0;0"

    color3 = Color("default")
    assert str(color3) == ""


def test_color_equality():
    """Test Color.__eq__ method."""
    # Same colors should be equal
    color1 = Color("indexed", 5)
    color2 = Color("indexed", 5)
    assert color1 == color2

    # Different colors should not be equal
    color3 = Color("indexed", 3)
    assert color1 != color3

    # Different modes should not be equal
    color4 = Color("rgb", (255, 0, 0))
    assert color1 != color4

    # Comparison with non-Color should return NotImplemented
    assert color1.__eq__("not a color") == NotImplemented
