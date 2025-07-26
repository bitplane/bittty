"""Tests for Style.diff method."""

from bittty.style import Style, Color


class TestStyleDiff:
    """Test Style.diff method for generating optimal ANSI transitions."""

    def test_diff_identical_styles_returns_empty(self):
        """Test that identical styles return empty string."""
        style1 = Style(fg=Color("rgb", (255, 0, 0)), bold=True)
        style2 = Style(fg=Color("rgb", (255, 0, 0)), bold=True)

        assert style1.diff(style2) == ""

    def test_diff_to_default_returns_reset(self):
        """Test that transitioning to default style returns reset."""
        colored_style = Style(fg=Color("rgb", (255, 0, 0)), bold=True)
        default_style = Style()

        assert colored_style.diff(default_style) == "\x1b[0m"

    def test_diff_from_default_returns_full_style(self):
        """Test that transitioning from default style returns full ANSI."""
        default_style = Style()
        colored_style = Style(fg=Color("rgb", (255, 0, 0)), bold=True)

        result = default_style.diff(colored_style)
        # Should contain both red color and bold
        assert "38;2;255;0;0" in result
        assert "1" in result
        assert result.startswith("\x1b[")
        assert result.endswith("m")

    def test_diff_complex_transition_uses_reset(self):
        """Test that complex transitions use reset+target for now."""
        style1 = Style(fg=Color("indexed", 1), bg=Color("indexed", 2), bold=True)
        style2 = Style(fg=Color("rgb", (255, 0, 0)), italic=True)

        result = style1.diff(style2)
        # Should start with reset
        assert result.startswith("\x1b[0m")
        # Should contain the target style
        assert "38;2;255;0;0" in result
        assert "3" in result  # italic

    def test_diff_only_foreground_change(self):
        """Test transition with only foreground color change."""
        style1 = Style(fg=Color("indexed", 1), bold=True)
        style2 = Style(fg=Color("indexed", 2), bold=True)

        result = style1.diff(style2)
        # For now, should use reset approach
        assert "\x1b[0m" in result
        assert "32" in result  # red foreground (indexed 2)
        assert "1" in result  # bold

    def test_diff_only_background_change(self):
        """Test transition with only background color change."""
        style1 = Style(bg=Color("indexed", 1), bold=True)
        style2 = Style(bg=Color("indexed", 2), bold=True)

        result = style1.diff(style2)
        assert "\x1b[0m" in result
        assert "42" in result  # green background (indexed 2)
        assert "1" in result  # bold

    def test_diff_rgb_colors(self):
        """Test transitions with RGB colors."""
        style1 = Style(fg=Color("rgb", (255, 0, 0)))
        style2 = Style(fg=Color("rgb", (0, 255, 0)))

        result = style1.diff(style2)
        assert "38;2;0;255;0" in result

    def test_diff_indexed_to_rgb(self):
        """Test transition from indexed to RGB color."""
        style1 = Style(fg=Color("indexed", 1))
        style2 = Style(fg=Color("rgb", (128, 64, 32)))

        result = style1.diff(style2)
        assert "38;2;128;64;32" in result

    def test_diff_attribute_changes(self):
        """Test transitions with attribute changes."""
        style1 = Style(bold=True, italic=False)
        style2 = Style(bold=False, italic=True)

        result = style1.diff(style2)
        assert "\x1b[0m" in result
        assert "3" in result  # italic

    def test_diff_add_attributes(self):
        """Test adding attributes to existing style."""
        style1 = Style(bold=True)
        style2 = Style(bold=True, italic=True, underline=True)

        result = style1.diff(style2)
        # Should include all target attributes
        assert "1" in result  # bold
        assert "3" in result  # italic
        assert "4" in result  # underline

    def test_diff_remove_attributes(self):
        """Test removing attributes from existing style."""
        style1 = Style(bold=True, italic=True, underline=True)
        style2 = Style(italic=True)

        result = style1.diff(style2)
        # Should use reset approach and only include italic
        assert "\x1b[0m" in result
        assert "3" in result  # italic
        # Should not contain bold or underline in final state

    def test_diff_mixed_color_and_attributes(self):
        """Test complex transitions with both colors and attributes."""
        style1 = Style(fg=Color("indexed", 1), bg=Color("rgb", (100, 100, 100)), bold=True, italic=False)
        style2 = Style(fg=Color("rgb", (255, 255, 0)), bg=Color("indexed", 4), bold=False, italic=True)

        result = style1.diff(style2)
        assert "\x1b[0m" in result
        assert "38;2;255;255;0" in result  # yellow fg
        assert "44" in result  # blue bg
        assert "3" in result  # italic

    def test_diff_caching_works(self):
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

    def test_diff_default_to_default_returns_empty(self):
        """Test that default to default transition returns empty."""
        default1 = Style()
        default2 = Style()

        assert default1.diff(default2) == ""

    def test_diff_preserves_style_objects(self):
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
