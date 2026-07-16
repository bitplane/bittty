from bittty.terminal import Terminal


def test_scroll_up():
    terminal = Terminal(width=10, height=5)
    # Fill terminal with content
    for i in range(terminal.height):
        terminal.current_buffer.set(0, i, f"Line {i}")

    # Set scroll region to cover entire terminal initially
    terminal.set_scroll_region(0, terminal.height - 1)

    # Scroll up by 1
    terminal.scroll_up(1)
    expected_lines = [
        "Line 1    ",
        "Line 2    ",
        "Line 3    ",
        "Line 4    ",
        "          ",
    ]
    assert [terminal.current_buffer.get_line_text(i) for i in range(terminal.height)] == expected_lines

    # Scroll up by 2
    terminal = Terminal(width=10, height=5)
    for i in range(terminal.height):
        terminal.current_buffer.set(0, i, f"Line {i}")
    terminal.set_scroll_region(0, terminal.height - 1)
    terminal.scroll_up(2)
    expected_lines = [
        "Line 2    ",
        "Line 3    ",
        "Line 4    ",
        "          ",
        "          ",
    ]
    assert [terminal.current_buffer.get_line_text(i) for i in range(terminal.height)] == expected_lines


def test_scroll_down():
    terminal = Terminal(width=10, height=5)
    # Fill terminal with content
    for i in range(terminal.height):
        terminal.current_buffer.set(0, i, f"Line {i}")

    # Set scroll region to cover entire terminal initially
    terminal.set_scroll_region(0, terminal.height - 1)

    # Scroll down by 1
    terminal.scroll_down(1)
    expected_lines = [
        "          ",
        "Line 0    ",
        "Line 1    ",
        "Line 2    ",
        "Line 3    ",
    ]
    assert [terminal.current_buffer.get_line_text(i) for i in range(terminal.height)] == expected_lines

    # Scroll down by 2
    terminal = Terminal(width=10, height=5)
    for i in range(terminal.height):
        terminal.current_buffer.set(0, i, f"Line {i}")
    terminal.set_scroll_region(0, terminal.height - 1)
    terminal.scroll_down(2)
    expected_lines = [
        "          ",
        "          ",
        "Line 0    ",
        "Line 1    ",
        "Line 2    ",
    ]
    assert [terminal.current_buffer.get_line_text(i) for i in range(terminal.height)] == expected_lines


def test_set_scroll_region():
    terminal = Terminal(width=10, height=10)
    terminal.set_scroll_region(2, 7)
    assert terminal.scroll_top == 2
    assert terminal.scroll_bottom == 7

    # Test clamping
    terminal.set_scroll_region(-1, 12)
    assert terminal.scroll_top == 0
    assert terminal.scroll_bottom == 9  # height - 1

    terminal.set_scroll_region(5, 3)  # top > bottom
    assert terminal.scroll_top == 5
    assert terminal.scroll_bottom == 5  # clamped to top


def test_line_feed_with_scrolling():
    terminal = Terminal(width=10, height=5)
    # Fill terminal up to the last line
    for i in range(terminal.height - 1):
        terminal.current_buffer.set(0, i, f"Line {i}")
    terminal.cursor_y = terminal.height - 1  # Cursor on the last line

    # Set scroll region to cover entire terminal
    terminal.set_scroll_region(0, terminal.height - 1)

    # Perform line feed, should scroll up
    terminal.line_feed()

    expected_lines = [
        "Line 1    ",
        "Line 2    ",
        "Line 3    ",
        "          ",
        "          ",
    ]
    assert [terminal.current_buffer.get_line_text(i) for i in range(terminal.height)] == expected_lines
    assert terminal.cursor_y == terminal.height - 1  # Cursor should remain on the last line
