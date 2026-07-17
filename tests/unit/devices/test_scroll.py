from bittty import Board


def test_scroll_up():
    board = Board(width=10, height=5)
    # Fill terminal with content
    for i in range(board.height):
        board.blitter.current_buffer.set(0, i, f"Line {i}")

    # Set scroll region to cover entire terminal initially
    board.blitter.set_scroll_region(0, board.height - 1)

    # Scroll up by 1
    board.blitter.scroll_up(1)
    expected_lines = [
        "Line 1    ",
        "Line 2    ",
        "Line 3    ",
        "Line 4    ",
        "          ",
    ]
    assert [board.blitter.current_buffer.get_line_text(i) for i in range(board.height)] == expected_lines

    # Scroll up by 2
    board = Board(width=10, height=5)
    for i in range(board.height):
        board.blitter.current_buffer.set(0, i, f"Line {i}")
    board.blitter.set_scroll_region(0, board.height - 1)
    board.blitter.scroll_up(2)
    expected_lines = [
        "Line 2    ",
        "Line 3    ",
        "Line 4    ",
        "          ",
        "          ",
    ]
    assert [board.blitter.current_buffer.get_line_text(i) for i in range(board.height)] == expected_lines


def test_scroll_down():
    board = Board(width=10, height=5)
    # Fill terminal with content
    for i in range(board.height):
        board.blitter.current_buffer.set(0, i, f"Line {i}")

    # Set scroll region to cover entire terminal initially
    board.blitter.set_scroll_region(0, board.height - 1)

    # Scroll down by 1
    board.blitter.scroll_down(1)
    expected_lines = [
        "          ",
        "Line 0    ",
        "Line 1    ",
        "Line 2    ",
        "Line 3    ",
    ]
    assert [board.blitter.current_buffer.get_line_text(i) for i in range(board.height)] == expected_lines

    # Scroll down by 2
    board = Board(width=10, height=5)
    for i in range(board.height):
        board.blitter.current_buffer.set(0, i, f"Line {i}")
    board.blitter.set_scroll_region(0, board.height - 1)
    board.blitter.scroll_down(2)
    expected_lines = [
        "          ",
        "          ",
        "Line 0    ",
        "Line 1    ",
        "Line 2    ",
    ]
    assert [board.blitter.current_buffer.get_line_text(i) for i in range(board.height)] == expected_lines


def test_set_scroll_region():
    board = Board(width=10, height=10)
    board.blitter.set_scroll_region(2, 7)
    assert board.blitter.scroll_top == 2
    assert board.blitter.scroll_bottom == 7

    # Test clamping
    board.blitter.set_scroll_region(-1, 12)
    assert board.blitter.scroll_top == 0
    assert board.blitter.scroll_bottom == 9  # height - 1

    board.blitter.set_scroll_region(5, 3)  # top > bottom
    assert board.blitter.scroll_top == 5
    assert board.blitter.scroll_bottom == 5  # clamped to top


def test_line_feed_with_scrolling():
    board = Board(width=10, height=5)
    # Fill terminal up to the last line
    for i in range(board.height - 1):
        board.blitter.current_buffer.set(0, i, f"Line {i}")
    board.cursor.y = board.height - 1  # Cursor on the last line

    # Set scroll region to cover entire terminal
    board.blitter.set_scroll_region(0, board.height - 1)

    # Perform line feed, should scroll up
    board.cursor.line_feed()

    expected_lines = [
        "Line 1    ",
        "Line 2    ",
        "Line 3    ",
        "          ",
        "          ",
    ]
    assert [board.blitter.current_buffer.get_line_text(i) for i in range(board.height)] == expected_lines
    assert board.cursor.y == board.height - 1  # Cursor should remain on the last line
