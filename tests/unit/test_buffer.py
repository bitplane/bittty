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
