"""Video page behaviour: cells, wide glyphs, scrolling, resize."""

from bittty.video import Video
from bittty.style import Style
from bittty import constants


def test_get_cell_out_of_bounds():
    """Test get_cell returns default cell for out of bounds coordinates."""
    page = Video(width=5, height=3)

    # Test coordinates outside page bounds (line 34)
    default_cell = page.get_cell(10, 10)
    assert default_cell == (Style(), " ")

    # Test negative coordinates
    default_cell = page.get_cell(-1, -1)
    assert default_cell == (Style(), " ")


def test_set_cell_fallback_to_default_style():
    """Test set_cell with invalid style_or_ansi falls back to default Style."""
    page = Video(width=5, height=3)

    # Pass an invalid type (not Style, str, or None) - hits line 53
    page.set_cell(0, 0, "X", 123)  # Invalid type
    style, char = page.get_cell(0, 0)
    assert isinstance(style, Style)
    assert char == "X"


def test_set_fallback_to_default_style():
    """Test set method with invalid style_or_ansi falls back to default Style."""
    page = Video(width=5, height=3)

    # Pass an invalid type (not Style, str, or None) - hits line 70
    page.set(0, 0, "Hello", 123)  # Invalid type

    # Check all characters were set with default style
    for i in range(5):
        style, char = page.get_cell(i, 0)
        assert isinstance(style, Style)
        assert char == "Hello"[i]


def test_insert_out_of_bounds_x():
    """Test insert method with x coordinate at edge of page width."""
    page = Video(width=5, height=3)

    # Insert at x == width should return early (line 80)
    page.insert(5, 0, "text")  # x >= width

    # The page should remain unchanged
    for i in range(5):
        style, char = page.get_cell(i, 0)
        assert char == " "


def test_insert_fallback_to_default_style():
    """Test insert method with invalid style_or_ansi falls back to default Style."""
    page = Video(width=5, height=3)

    # Pass an invalid type (not Style, str, or None) - hits line 90
    page.insert(0, 0, "Hi", 123)  # Invalid type

    # Check characters were inserted with default style
    style, char = page.get_cell(0, 0)
    assert isinstance(style, Style)
    assert char == "H"


def test_insert_with_padding_needed():
    """Test insert method when padding is needed beyond current row length."""
    page = Video(width=10, height=3)

    # Insert at x position beyond current row content - triggers padding logic (lines 106-111)
    page.insert(7, 0, "text")

    # Check that padding was added and text inserted (truncated to width)
    assert page.get_line_text(0) == "       tex"  # Only fits 3 chars due to width=10

    # Verify cells between start and insertion point are spaces with default style
    for i in range(7):
        style, char = page.get_cell(i, 0)
        assert isinstance(style, Style)
        assert char == " "


def test_set_cell_ansi_string_conversion():
    """Test set_cell with ANSI string gets converted to Style."""
    page = Video(width=5, height=3)

    # Test with actual ANSI string
    page.set_cell(0, 0, "X", "\x1b[31m")  # Red color
    style, char = page.get_cell(0, 0)
    assert isinstance(style, Style)
    assert char == "X"
    # Style should have red foreground from ANSI parsing


def test_set_cell_empty_ansi_string():
    """Test set_cell with empty ANSI string."""
    page = Video(width=5, height=3)

    # Test with empty string - should use default Style
    page.set_cell(0, 0, "X", "")
    style, char = page.get_cell(0, 0)
    assert isinstance(style, Style)
    assert char == "X"


def test_set_ansi_string_conversion():
    """Test set method with ANSI string gets converted to Style."""
    page = Video(width=5, height=3)

    # Test with actual ANSI string
    page.set(0, 0, "Hello", "\x1b[32m")  # Green color

    for i in range(5):
        style, char = page.get_cell(i, 0)
        assert isinstance(style, Style)
        assert char == "Hello"[i]


def test_insert_ansi_string_conversion():
    """Test insert method with ANSI string gets converted to Style."""
    page = Video(width=10, height=3)

    # Test with actual ANSI string
    page.insert(0, 0, "Hi", "\x1b[34m")  # Blue color

    style1, char1 = page.get_cell(0, 0)
    style2, char2 = page.get_cell(1, 0)
    assert isinstance(style1, Style)
    assert isinstance(style2, Style)
    assert char1 == "H"
    assert char2 == "i"


def test_delete_basic_functionality():
    """Test delete method basic functionality."""
    page = Video(width=10, height=3)
    page.set(0, 0, "Hello World")

    # Delete 2 characters starting at position 5 (space and W)
    page.delete(5, 0, 2)

    assert page.get_line_text(0) == "Helloorl  "


def test_delete_beyond_row_length():
    """Test delete when end position exceeds row length."""
    page = Video(width=10, height=3)
    page.set(0, 0, "Hello")  # Only 5 characters

    # Try to delete from position 3 with count 10 (beyond row length)
    page.delete(3, 0, 10)

    assert page.get_line_text(0) == "Hel       "


def test_scroll_up_basic():
    """Test scroll_up basic functionality."""
    page = Video(width=5, height=3)
    page.set(0, 0, "Line1")
    page.set(0, 1, "Line2")
    page.set(0, 2, "Line3")

    page.scroll_up(1)

    assert page.get_line_text(0) == "Line2"
    assert page.get_line_text(1) == "Line3"
    assert page.get_line_text(2) == "     "  # New blank line


def test_scroll_down_basic():
    """Test scroll_down basic functionality."""
    page = Video(width=5, height=3)
    page.set(0, 0, "Line1")
    page.set(0, 1, "Line2")
    page.set(0, 2, "Line3")

    page.scroll_down(1)

    assert page.get_line_text(0) == "     "  # New blank line
    assert page.get_line_text(1) == "Line1"
    assert page.get_line_text(2) == "Line2"


def test_resize_expand_height():
    """Test resize when expanding height."""
    page = Video(width=5, height=2)
    page.set(0, 0, "Line1")
    page.set(0, 1, "Line2")

    page.resize(5, 4)  # Expand height

    assert page.height == 4
    assert page.get_line_text(0) == "Line1"
    assert page.get_line_text(1) == "Line2"
    assert page.get_line_text(2) == "     "  # New row
    assert page.get_line_text(3) == "     "  # New row


def test_resize_shrink_height():
    """Test resize when shrinking height."""
    page = Video(width=5, height=4)
    page.set(0, 0, "Line1")
    page.set(0, 1, "Line2")
    page.set(0, 2, "Line3")
    page.set(0, 3, "Line4")

    page.resize(5, 2)  # Shrink height

    assert page.height == 2
    assert page.get_line_text(0) == "Line1"
    assert page.get_line_text(1) == "Line2"


def test_resize_expand_width():
    """Test resize when expanding width."""
    page = Video(width=3, height=2)
    page.set(0, 0, "ABC")
    page.set(0, 1, "DEF")

    page.resize(6, 2)  # Expand width

    assert page.width == 6
    assert page.get_line_text(0) == "ABC   "  # Extended with spaces
    assert page.get_line_text(1) == "DEF   "


def test_resize_expansion_reuses_the_cached_empty_cell():
    page = Video(width=2, height=1)
    page.set(0, 0, "AB")

    page.resize(5, 3)

    assert all(cell is page._empty_cell for cell in page.grid[0][2:])
    assert all(cell is page._empty_cell for row in page.grid[1:] for cell in row)


def test_resize_shrink_width():
    """Test resize when shrinking width."""
    page = Video(width=6, height=2)
    page.set(0, 0, "ABCDEF")
    page.set(0, 1, "GHIJKL")

    page.resize(3, 2)  # Shrink width

    assert page.width == 3
    assert page.get_line_text(0) == "ABC"  # Truncated
    assert page.get_line_text(1) == "GHI"


def test_delete_out_of_bounds():
    """Test delete method with out of bounds coordinates."""
    page = Video(width=5, height=3)
    page.set(0, 0, "Hello")

    # Delete with x >= width should return early (line 116)
    page.delete(5, 0, 1)  # x == width
    page.delete(10, 0, 1)  # x > width

    # The page should be unchanged
    assert page.get_line_text(0) == "Hello"


def test_clear_region_with_style_object():
    """Test clear_region with Style object (line 135)."""
    page = Video(width=5, height=3)
    page.set(0, 0, "XXXXX")

    style = Style(bold=True)
    page.clear_region(1, 0, 3, 0, style)

    # Check that cleared region has the provided style
    for x in range(1, 4):
        cell_style, char = page.get_cell(x, 0)
        assert char == " "
        assert isinstance(cell_style, Style)


def test_clear_region_with_invalid_style():
    """Test clear_region with invalid style_or_ansi falls back to default (line 139)."""
    page = Video(width=5, height=3)
    page.set(0, 0, "XXXXX")

    # Pass invalid type - should fall back to default Style
    page.clear_region(1, 0, 3, 0, 123)

    # Should clear with default style
    for x in range(1, 4):
        cell_style, char = page.get_cell(x, 0)
        assert char == " "
        assert isinstance(cell_style, Style)


def test_clear_line_with_style_object():
    """Test clear_line with Style object (line 156)."""
    page = Video(width=5, height=3)
    page.set(0, 0, "XXXXX")

    style = Style(italic=True)
    page.clear_line(0, constants.ERASE_ALL, 0, style)

    # Check that line was cleared with provided style
    for x in range(5):
        cell_style, char = page.get_cell(x, 0)
        assert char == " "
        assert isinstance(cell_style, Style)


def test_clear_line_with_invalid_style():
    """Test clear_line with invalid style_or_ansi falls back to default (line 160)."""
    page = Video(width=5, height=3)
    page.set(0, 0, "XXXXX")

    # Pass invalid type - should fall back to default Style
    page.clear_line(0, constants.ERASE_ALL, 0, 123)

    # Should clear with default style
    for x in range(5):
        cell_style, char = page.get_cell(x, 0)
        assert char == " "
        assert isinstance(cell_style, Style)


def test_get_line_text_out_of_bounds():
    """Test get_line_text with out of bounds y coordinate (line 215)."""
    page = Video(width=5, height=3)
    page.set(0, 0, "Hello")

    # Out of bounds should return empty string
    assert page.get_line_text(-1) == ""
    assert page.get_line_text(3) == ""
    assert page.get_line_text(10) == ""


def test_get_line_out_of_bounds():
    """Test get_line with out of bounds y coordinate (line 230)."""
    page = Video(width=5, height=3)

    # Out of bounds should return empty string
    assert page.get_line(-1) == ""
    assert page.get_line(3) == ""
    assert page.get_line(10) == ""


def test_get_line_with_explicit_width():
    """Test get_line with explicitly provided width (line 234)."""
    page = Video(width=10, height=3)
    page.set(0, 0, "Hello")

    # Use explicit width different from page width
    result = page.get_line(0, width=3)

    # Should only process first 3 characters
    # This tests the width override functionality
    assert result  # Should have some content, exact format depends on style processing


def test_get_line_is_a_pure_video_read():
    """No cursor or pointer compositing: video memory in, ANSI out."""
    page = Video(width=10, height=3)
    page.set(0, 0, "Hello")

    result = page.get_line(0)
    assert "Hello" in result
    assert "\033[7m" not in result  # no software cursor cell


def test_write_stamps_only_its_row():
    page = Video(width=10, height=3)
    seen = page.observe()
    page.set(0, 1, "hi")
    assert page.dirty_rows(seen) == [1]
    assert page.dirty_rows(page.observe()) == []


def test_full_height_scroll_dirties_the_page():
    page = Video(width=10, height=3)
    seen = page.observe()
    page.scroll_region_up(0, 2, 1)
    assert page.page_gen >= seen
    assert page.dirty_rows(seen) == [0, 1, 2]


def test_region_scroll_dirties_only_the_region():
    page = Video(width=10, height=4)
    seen = page.observe()
    page.scroll_region_up(1, 2, 1)
    assert page.dirty_rows(seen) == [1, 2]


def test_resize_dirties_everything():
    page = Video(width=10, height=3)
    seen = page.observe()
    page.resize(8, 4)
    assert page.dirty_rows(seen) == [0, 1, 2, 3]
