from bittty.terminal import Terminal
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT, DECAWM_AUTOWRAP, IRM_INSERT_REPLACE


def test_resize():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.cursor_x = 70
    terminal.cursor_y = 20

    terminal.resize(100, 30)
    assert terminal.width == 100
    assert terminal.height == 30
    assert terminal.cursor_x == 70  # Cursor should remain if within bounds
    assert terminal.cursor_y == 20
    assert terminal.scroll_bottom == 29  # Should adjust to new height

    terminal.resize(50, 10)
    assert terminal.width == 50
    assert terminal.height == 10
    assert terminal.cursor_x == 49  # Cursor should clamp to new width
    assert terminal.cursor_y == 9  # Cursor should clamp to new height
    assert terminal.scroll_bottom == 9


def test_alternate_terminal_switching():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    assert not terminal.in_alt_screen
    assert terminal.current_buffer == terminal.primary_buffer

    terminal.alternate_screen_on()
    assert terminal.in_alt_screen
    assert terminal.current_buffer == terminal.alt_buffer

    # Calling again should do nothing
    terminal.alternate_screen_on()
    assert terminal.in_alt_screen
    assert terminal.current_buffer == terminal.alt_buffer

    terminal.alternate_screen_off()
    assert not terminal.in_alt_screen
    assert terminal.current_buffer == terminal.primary_buffer

    # Calling again should do nothing
    terminal.alternate_screen_off()
    assert not terminal.in_alt_screen
    assert terminal.current_buffer == terminal.primary_buffer


def test_alignment_test():
    terminal = Terminal(width=10, height=5)
    terminal.alignment_test()

    expected_char = "E"
    for y in range(terminal.height):
        line_text = terminal.current_buffer.get_line_text(y)
        assert len(line_text) == terminal.width
        assert all(char == expected_char for char in line_text)


def test_alternate_terminal_on_off_restores_lines():
    terminal = Terminal(width=10, height=5)
    terminal.current_buffer.set(0, 0, "Hello")
    terminal.alternate_screen_on()
    assert terminal.current_buffer.get_line_text(0) == "          "
    terminal.alternate_screen_off()
    assert terminal.current_buffer.get_line_text(0) == "Hello     "


def test_set_and_clear_modes():
    terminal = Terminal(width=80, height=24)

    # Test setting a private mode
    terminal.set_mode(DECAWM_AUTOWRAP, private=True)
    assert terminal.auto_wrap

    # Test clearing a private mode
    terminal.clear_mode(DECAWM_AUTOWRAP, private=True)
    assert not terminal.auto_wrap

    # Test setting a non-private mode
    terminal.set_mode(IRM_INSERT_REPLACE, private=False)
    assert terminal.insert_mode

    # Test clearing a non-private mode
    terminal.clear_mode(IRM_INSERT_REPLACE, private=False)
    assert not terminal.insert_mode

    # Test an unknown mode
    terminal.set_mode(999, private=True)
    # No attribute should be set
    assert not hasattr(terminal, "unknown_mode")
