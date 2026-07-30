"""Tests for scroll region functionality."""

from bittty import Board
from bittty.style import parse_sgr_sequence
from bittty.video import CONTINUATION, WideHead


def test_scroll_up_within_region():
    """Test scrolling up within a constrained scroll region."""
    board = Board(width=10, height=10)

    # Fill terminal with numbered lines
    for i in range(10):
        board.blitter.current_buffer.set(0, i, f"Line {i}")

    # Set scroll region to middle of terminal (rows 3-7, 0-based)
    board.blitter.set_scroll_region(3, 7)

    # Scroll up by 1 within the region
    board.blitter.scroll_up(1)

    # Lines 0-2 should be unchanged
    assert board.blitter.current_buffer.get_line_text(0) == "Line 0    "
    assert board.blitter.current_buffer.get_line_text(1) == "Line 1    "
    assert board.blitter.current_buffer.get_line_text(2) == "Line 2    "

    # Lines 3-7 should have scrolled up
    assert board.blitter.current_buffer.get_line_text(3) == "Line 4    "
    assert board.blitter.current_buffer.get_line_text(4) == "Line 5    "
    assert board.blitter.current_buffer.get_line_text(5) == "Line 6    "
    assert board.blitter.current_buffer.get_line_text(6) == "Line 7    "
    assert board.blitter.current_buffer.get_line_text(7) == "          "

    # Lines 8-9 should be unchanged
    assert board.blitter.current_buffer.get_line_text(8) == "Line 8    "
    assert board.blitter.current_buffer.get_line_text(9) == "Line 9    "


def test_scroll_down_within_region():
    """Test scrolling down within a constrained scroll region."""
    board = Board(width=10, height=10)

    # Fill terminal with numbered lines
    for i in range(10):
        board.blitter.current_buffer.set(0, i, f"Line {i}")

    # Set scroll region to middle of terminal (rows 3-7, 0-based)
    board.blitter.set_scroll_region(3, 7)

    # Scroll down by 1 within the region
    board.blitter.scroll_down(1)

    # Lines 0-2 should be unchanged
    assert board.blitter.current_buffer.get_line_text(0) == "Line 0    "
    assert board.blitter.current_buffer.get_line_text(1) == "Line 1    "
    assert board.blitter.current_buffer.get_line_text(2) == "Line 2    "

    # Lines 3-7 should have scrolled down
    assert board.blitter.current_buffer.get_line_text(3) == "          "
    assert board.blitter.current_buffer.get_line_text(4) == "Line 3    "
    assert board.blitter.current_buffer.get_line_text(5) == "Line 4    "
    assert board.blitter.current_buffer.get_line_text(6) == "Line 5    "
    assert board.blitter.current_buffer.get_line_text(7) == "Line 6    "

    # Lines 8-9 should be unchanged
    assert board.blitter.current_buffer.get_line_text(8) == "Line 8    "
    assert board.blitter.current_buffer.get_line_text(9) == "Line 9    "


def test_line_feed_at_bottom_of_scroll_region():
    """Test line feed when cursor is at bottom of scroll region."""
    board = Board(width=10, height=10)

    # Fill terminal with numbered lines
    for i in range(10):
        board.blitter.current_buffer.set(0, i, f"Line {i}")

    # Set scroll region to rows 2-5 (0-based)
    board.blitter.set_scroll_region(2, 5)

    # Place cursor at bottom of scroll region
    board.cursor.y = 5

    # Line feed should trigger scroll within region
    board.cursor.line_feed()

    # Lines outside region should be unchanged
    assert board.blitter.current_buffer.get_line_text(0) == "Line 0    "
    assert board.blitter.current_buffer.get_line_text(1) == "Line 1    "
    assert board.blitter.current_buffer.get_line_text(6) == "Line 6    "
    assert board.blitter.current_buffer.get_line_text(7) == "Line 7    "
    assert board.blitter.current_buffer.get_line_text(8) == "Line 8    "
    assert board.blitter.current_buffer.get_line_text(9) == "Line 9    "

    # Lines within region should have scrolled up
    assert board.blitter.current_buffer.get_line_text(2) == "Line 3    "
    assert board.blitter.current_buffer.get_line_text(3) == "Line 4    "
    assert board.blitter.current_buffer.get_line_text(4) == "Line 5    "
    assert board.blitter.current_buffer.get_line_text(5) == "          "


def test_multiple_scroll_regions():
    """Test changing scroll regions and scrolling."""
    board = Board(width=10, height=10)

    # Fill terminal with numbered lines
    for i in range(10):
        board.blitter.current_buffer.set(0, i, f"Line {i}")

    # Set first scroll region (top half)
    board.blitter.set_scroll_region(0, 4)
    board.blitter.scroll_up(1)

    # Top half should be scrolled
    assert board.blitter.current_buffer.get_line_text(0) == "Line 1    "
    assert board.blitter.current_buffer.get_line_text(4) == "          "

    # Bottom half should be unchanged
    assert board.blitter.current_buffer.get_line_text(5) == "Line 5    "
    assert board.blitter.current_buffer.get_line_text(9) == "Line 9    "

    # Change scroll region to bottom half
    board.blitter.set_scroll_region(5, 9)
    board.blitter.scroll_up(1)

    # Top half should remain as it was
    assert board.blitter.current_buffer.get_line_text(0) == "Line 1    "
    assert board.blitter.current_buffer.get_line_text(4) == "          "

    # Bottom half should now be scrolled
    assert board.blitter.current_buffer.get_line_text(5) == "Line 6    "
    assert board.blitter.current_buffer.get_line_text(9) == "          "


def test_reset_scroll_region():
    """Test resetting scroll region with CSI r."""
    board = Board(width=10, height=10)

    # Set a custom scroll region
    board.blitter.set_scroll_region(3, 6)
    assert board.blitter.scroll_top == 3
    assert board.blitter.scroll_bottom == 6

    # Reset should restore full terminal
    board.blitter.set_scroll_region(0, 9)  # This is what CSI r with no params should do
    assert board.blitter.scroll_top == 0
    assert board.blitter.scroll_bottom == 9


def test_tmux_style_scroll_only_moves_the_margin_rectangle():
    board = Board(width=10, height=6)
    buffer = board.blitter.current_buffer
    for y in range(6):
        buffer.set(0, y, str(y) * 10)

    # Rows 2..5, columns 3..8: the shape tmux uses to scroll one pane
    # without disturbing its neighbour or status row.
    board.parser.feed("\x1b[2;5r\x1b[?69h\x1b[3;8s\x1b[S")

    assert [buffer.get_line_text(y) for y in range(6)] == [
        "0000000000",
        "1122222211",
        "2233333322",
        "3344444433",
        "44      44",
        "5555555555",
    ]


def test_rectangular_scroll_down_preserves_cells_outside_margins():
    board = Board(width=10, height=6)
    buffer = board.blitter.current_buffer
    for y in range(6):
        buffer.set(0, y, str(y) * 10)

    board.parser.feed("\x1b[2;5r\x1b[?69h\x1b[3;8s\x1b[T")

    assert [buffer.get_line_text(y) for y in range(6)] == [
        "0000000000",
        "11      11",
        "2211111122",
        "3322222233",
        "4433333344",
        "5555555555",
    ]


def test_insert_and_delete_lines_honour_left_right_margins():
    board = Board(width=8, height=5)
    buffer = board.blitter.current_buffer
    for y in range(5):
        buffer.set(0, y, str(y) * 8)

    board.parser.feed("\x1b[?69h\x1b[3;6s\x1b[2;4H\x1b[L")
    assert [buffer.get_line_text(y) for y in range(5)] == [
        "00000000",
        "11    11",
        "22111122",
        "33222233",
        "44333344",
    ]

    board = Board(width=8, height=5)
    buffer = board.blitter.current_buffer
    for y in range(5):
        buffer.set(0, y, str(y) * 8)
    board.parser.feed("\x1b[?69h\x1b[3;6s\x1b[2;4H\x1b[M")
    assert [buffer.get_line_text(y) for y in range(5)] == [
        "00000000",
        "11222211",
        "22333322",
        "33444433",
        "44    44",
    ]


def test_rectangular_scroll_uses_current_background_for_vacated_cells():
    board = Board(width=6, height=3)
    buffer = board.blitter.current_buffer
    for y in range(3):
        buffer.set(0, y, str(y) * 6)

    board.parser.feed("\x1b[?69h\x1b[2;5s\x1b[42m\x1b[S")

    green = parse_sgr_sequence("\x1b[42m")
    assert buffer.get_line_text(2) == "2    2"
    assert all(buffer.get_cell(x, 2) == (green, " ") for x in range(1, 5))


def test_rectangular_scroll_does_not_leave_split_wide_glyphs():
    board = Board(width=8, height=3)
    buffer = board.blitter.current_buffer
    buffer.set(0, 0, "abcdefgh")
    buffer.set(0, 1, "abcdefgh")
    buffer.set(1, 1, "❌")
    buffer.set(5, 1, "❌")

    # Both glyphs in the source row cross a margin edge.
    board.parser.feed("\x1b[?69h\x1b[3;6s\x1b[S")

    for row in buffer.grid:
        for x, (_, char) in enumerate(row):
            if char == CONTINUATION:
                assert x > 0 and isinstance(row[x - 1][1], WideHead)
            if isinstance(char, WideHead):
                assert x + 1 < board.width and row[x + 1][1] == CONTINUATION
