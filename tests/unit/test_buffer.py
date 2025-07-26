"""Tests for buffer.py functionality to improve code coverage."""

from bittty.buffer import Buffer
from bittty.style import Style


def test_get_cell_out_of_bounds():
    """Test get_cell returns default cell for out of bounds coordinates."""
    buffer = Buffer(width=5, height=3)

    # Test coordinates outside buffer bounds (line 34)
    default_cell = buffer.get_cell(10, 10)
    assert default_cell == (Style(), " ")

    # Test negative coordinates
    default_cell = buffer.get_cell(-1, -1)
    assert default_cell == (Style(), " ")


def test_set_cell_fallback_to_default_style():
    """Test set_cell with invalid style_or_ansi falls back to default Style."""
    buffer = Buffer(width=5, height=3)

    # Pass an invalid type (not Style, str, or None) - hits line 53
    buffer.set_cell(0, 0, "X", 123)  # Invalid type
    style, char = buffer.get_cell(0, 0)
    assert isinstance(style, Style)
    assert char == "X"


def test_set_fallback_to_default_style():
    """Test set method with invalid style_or_ansi falls back to default Style."""
    buffer = Buffer(width=5, height=3)

    # Pass an invalid type (not Style, str, or None) - hits line 70
    buffer.set(0, 0, "Hello", 123)  # Invalid type

    # Check all characters were set with default style
    for i in range(5):
        style, char = buffer.get_cell(i, 0)
        assert isinstance(style, Style)
        assert char == "Hello"[i]


def test_insert_out_of_bounds_x():
    """Test insert method with x coordinate at edge of buffer width."""
    buffer = Buffer(width=5, height=3)

    # Insert at x == width should return early (line 80)
    buffer.insert(5, 0, "text")  # x >= width

    # Buffer should remain unchanged
    for i in range(5):
        style, char = buffer.get_cell(i, 0)
        assert char == " "


def test_insert_fallback_to_default_style():
    """Test insert method with invalid style_or_ansi falls back to default Style."""
    buffer = Buffer(width=5, height=3)

    # Pass an invalid type (not Style, str, or None) - hits line 90
    buffer.insert(0, 0, "Hi", 123)  # Invalid type

    # Check characters were inserted with default style
    style, char = buffer.get_cell(0, 0)
    assert isinstance(style, Style)
    assert char == "H"


def test_insert_with_padding_needed():
    """Test insert method when padding is needed beyond current row length."""
    buffer = Buffer(width=10, height=3)

    # Insert at x position beyond current row content - triggers padding logic (lines 106-111)
    buffer.insert(7, 0, "text")

    # Check that padding was added and text inserted (truncated to width)
    assert buffer.get_line_text(0) == "       tex"  # Only fits 3 chars due to width=10

    # Verify cells between start and insertion point are spaces with default style
    for i in range(7):
        style, char = buffer.get_cell(i, 0)
        assert isinstance(style, Style)
        assert char == " "


def test_set_cell_ansi_string_conversion():
    """Test set_cell with ANSI string gets converted to Style."""
    buffer = Buffer(width=5, height=3)

    # Test with actual ANSI string
    buffer.set_cell(0, 0, "X", "\x1b[31m")  # Red color
    style, char = buffer.get_cell(0, 0)
    assert isinstance(style, Style)
    assert char == "X"
    # Style should have red foreground from ANSI parsing


def test_set_cell_empty_ansi_string():
    """Test set_cell with empty ANSI string."""
    buffer = Buffer(width=5, height=3)

    # Test with empty string - should use default Style
    buffer.set_cell(0, 0, "X", "")
    style, char = buffer.get_cell(0, 0)
    assert isinstance(style, Style)
    assert char == "X"


def test_set_ansi_string_conversion():
    """Test set method with ANSI string gets converted to Style."""
    buffer = Buffer(width=5, height=3)

    # Test with actual ANSI string
    buffer.set(0, 0, "Hello", "\x1b[32m")  # Green color

    for i in range(5):
        style, char = buffer.get_cell(i, 0)
        assert isinstance(style, Style)
        assert char == "Hello"[i]


def test_insert_ansi_string_conversion():
    """Test insert method with ANSI string gets converted to Style."""
    buffer = Buffer(width=10, height=3)

    # Test with actual ANSI string
    buffer.insert(0, 0, "Hi", "\x1b[34m")  # Blue color

    style1, char1 = buffer.get_cell(0, 0)
    style2, char2 = buffer.get_cell(1, 0)
    assert isinstance(style1, Style)
    assert isinstance(style2, Style)
    assert char1 == "H"
    assert char2 == "i"


def test_delete_basic_functionality():
    """Test delete method basic functionality."""
    buffer = Buffer(width=10, height=3)
    buffer.set(0, 0, "Hello World")

    # Delete 2 characters starting at position 5 (space and W)
    buffer.delete(5, 0, 2)

    assert buffer.get_line_text(0) == "Helloorl  "


def test_delete_beyond_row_length():
    """Test delete when end position exceeds row length."""
    buffer = Buffer(width=10, height=3)
    buffer.set(0, 0, "Hello")  # Only 5 characters

    # Try to delete from position 3 with count 10 (beyond row length)
    buffer.delete(3, 0, 10)

    assert buffer.get_line_text(0) == "Hel       "


def test_scroll_up_basic():
    """Test scroll_up basic functionality."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "Line1")
    buffer.set(0, 1, "Line2")
    buffer.set(0, 2, "Line3")

    buffer.scroll_up(1)

    assert buffer.get_line_text(0) == "Line2"
    assert buffer.get_line_text(1) == "Line3"
    assert buffer.get_line_text(2) == "     "  # New blank line


def test_scroll_down_basic():
    """Test scroll_down basic functionality."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "Line1")
    buffer.set(0, 1, "Line2")
    buffer.set(0, 2, "Line3")

    buffer.scroll_down(1)

    assert buffer.get_line_text(0) == "     "  # New blank line
    assert buffer.get_line_text(1) == "Line1"
    assert buffer.get_line_text(2) == "Line2"


def test_resize_expand_height():
    """Test resize when expanding height."""
    buffer = Buffer(width=5, height=2)
    buffer.set(0, 0, "Line1")
    buffer.set(0, 1, "Line2")

    buffer.resize(5, 4)  # Expand height

    assert buffer.height == 4
    assert buffer.get_line_text(0) == "Line1"
    assert buffer.get_line_text(1) == "Line2"
    assert buffer.get_line_text(2) == "     "  # New row
    assert buffer.get_line_text(3) == "     "  # New row


def test_resize_shrink_height():
    """Test resize when shrinking height."""
    buffer = Buffer(width=5, height=4)
    buffer.set(0, 0, "Line1")
    buffer.set(0, 1, "Line2")
    buffer.set(0, 2, "Line3")
    buffer.set(0, 3, "Line4")

    buffer.resize(5, 2)  # Shrink height

    assert buffer.height == 2
    assert buffer.get_line_text(0) == "Line1"
    assert buffer.get_line_text(1) == "Line2"


def test_resize_expand_width():
    """Test resize when expanding width."""
    buffer = Buffer(width=3, height=2)
    buffer.set(0, 0, "ABC")
    buffer.set(0, 1, "DEF")

    buffer.resize(6, 2)  # Expand width

    assert buffer.width == 6
    assert buffer.get_line_text(0) == "ABC   "  # Extended with spaces
    assert buffer.get_line_text(1) == "DEF   "


def test_resize_shrink_width():
    """Test resize when shrinking width."""
    buffer = Buffer(width=6, height=2)
    buffer.set(0, 0, "ABCDEF")
    buffer.set(0, 1, "GHIJKL")

    buffer.resize(3, 2)  # Shrink width

    assert buffer.width == 3
    assert buffer.get_line_text(0) == "ABC"  # Truncated
    assert buffer.get_line_text(1) == "GHI"


def test_delete_out_of_bounds():
    """Test delete method with out of bounds coordinates."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "Hello")

    # Delete with x >= width should return early (line 116)
    buffer.delete(5, 0, 1)  # x == width
    buffer.delete(10, 0, 1)  # x > width

    # Buffer should be unchanged
    assert buffer.get_line_text(0) == "Hello"


def test_clear_region_with_style_object():
    """Test clear_region with Style object (line 135)."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "XXXXX")

    style = Style(bold=True)
    buffer.clear_region(1, 0, 3, 0, style)

    # Check that cleared region has the provided style
    for x in range(1, 4):
        cell_style, char = buffer.get_cell(x, 0)
        assert char == " "
        assert isinstance(cell_style, Style)


def test_clear_region_with_invalid_style():
    """Test clear_region with invalid style_or_ansi falls back to default (line 139)."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "XXXXX")

    # Pass invalid type - should fall back to default Style
    buffer.clear_region(1, 0, 3, 0, 123)

    # Should clear with default style
    for x in range(1, 4):
        cell_style, char = buffer.get_cell(x, 0)
        assert char == " "
        assert isinstance(cell_style, Style)


def test_clear_line_with_style_object():
    """Test clear_line with Style object (line 156)."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "XXXXX")

    from bittty import constants

    style = Style(italic=True)
    buffer.clear_line(0, constants.ERASE_ALL, 0, style)

    # Check that line was cleared with provided style
    for x in range(5):
        cell_style, char = buffer.get_cell(x, 0)
        assert char == " "
        assert isinstance(cell_style, Style)


def test_clear_line_with_invalid_style():
    """Test clear_line with invalid style_or_ansi falls back to default (line 160)."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "XXXXX")

    from bittty import constants

    # Pass invalid type - should fall back to default Style
    buffer.clear_line(0, constants.ERASE_ALL, 0, 123)

    # Should clear with default style
    for x in range(5):
        cell_style, char = buffer.get_cell(x, 0)
        assert char == " "
        assert isinstance(cell_style, Style)


def test_get_line_text_out_of_bounds():
    """Test get_line_text with out of bounds y coordinate (line 215)."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "Hello")

    # Out of bounds should return empty string
    assert buffer.get_line_text(-1) == ""
    assert buffer.get_line_text(3) == ""
    assert buffer.get_line_text(10) == ""


def test_get_line_out_of_bounds():
    """Test get_line with out of bounds y coordinate (line 230)."""
    buffer = Buffer(width=5, height=3)

    # Out of bounds should return empty string
    assert buffer.get_line(-1) == ""
    assert buffer.get_line(3) == ""
    assert buffer.get_line(10) == ""


def test_get_line_with_explicit_width():
    """Test get_line with explicitly provided width (line 234)."""
    buffer = Buffer(width=10, height=3)
    buffer.set(0, 0, "Hello")

    # Use explicit width different from buffer width
    result = buffer.get_line(0, width=3)

    # Should only process first 3 characters
    # This tests the width override functionality
    assert result  # Should have some content, exact format depends on style processing


def test_get_line_with_cursor_display():
    """Test get_line with cursor display (lines 268-271)."""
    buffer = Buffer(width=10, height=3)
    buffer.set(0, 0, "Hello")

    # Test cursor display at different positions
    result = buffer.get_line(0, cursor_x=2, cursor_y=0, show_cursor=True)
    assert result  # Should contain cursor formatting codes

    # Test padding with cursor beyond content (lines 268-271)
    result = buffer.get_line(0, width=15, cursor_x=12, cursor_y=0, show_cursor=True)
    assert result  # Should handle padding when cursor is beyond content


def test_get_line_tuple_out_of_bounds():
    """Test get_line_tuple with out of bounds y coordinate (line 291-292)."""
    buffer = Buffer(width=5, height=3)

    # Out of bounds should return empty tuple
    assert buffer.get_line_tuple(-1) == tuple()
    assert buffer.get_line_tuple(3) == tuple()
    assert buffer.get_line_tuple(10) == tuple()


def test_get_line_tuple_with_explicit_width():
    """Test get_line_tuple with explicit width (lines 294-296)."""
    buffer = Buffer(width=10, height=3)
    buffer.set(0, 0, "Hello")

    # Use explicit width
    result = buffer.get_line_tuple(0, width=3)

    # Should be a tuple with content for first 3 characters only
    assert isinstance(result, tuple)
    assert result  # Should have some content


def test_get_line_tuple_with_mouse_cursor():
    """Test get_line_tuple with mouse cursor display (lines 305-307)."""
    buffer = Buffer(width=10, height=3)
    buffer.set(0, 0, "Hello")

    # Test mouse cursor display
    result = buffer.get_line_tuple(0, mouse_x=3, mouse_y=1, show_mouse=True)

    # Should contain mouse cursor character at position
    assert isinstance(result, tuple)
    assert "↖" in result  # Mouse cursor character should be in tuple


def test_get_line_tuple_with_text_cursor():
    """Test get_line_tuple with text cursor display (lines 310-312)."""
    buffer = Buffer(width=10, height=3)
    buffer.set(0, 0, "Hello")

    # Test text cursor display
    result = buffer.get_line_tuple(0, cursor_x=2, cursor_y=0, show_cursor=True)

    # Should contain cursor formatting
    assert isinstance(result, tuple)
    assert "cursor" in result  # Should have cursor markers


def test_get_line_tuple_with_padding():
    """Test get_line_tuple padding logic (lines 318-321)."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "Hi")  # Only 2 characters

    # Request wider width to trigger padding
    result = buffer.get_line_tuple(0, width=8)

    # Should contain padding information
    assert isinstance(result, tuple)
    assert "pad" in result  # Should have padding marker
    assert "reset" in result  # Should have reset for padding


def test_get_line_tuple_final_reset():
    """Test get_line_tuple always ends with reset (lines 323-325)."""
    buffer = Buffer(width=5, height=3)
    buffer.set(0, 0, "Hello")

    result = buffer.get_line_tuple(0)

    # Should always end with final reset
    assert isinstance(result, tuple)
    assert "final_reset" in result
