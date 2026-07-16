from bittty.terminal import Terminal
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT, DECAWM_AUTOWRAP, IRM_INSERT_REPLACE


def test_resize():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    terminal.board.cursor.x = 70
    terminal.board.cursor.y = 20

    terminal.resize(100, 30)
    assert terminal.width == 100
    assert terminal.height == 30
    assert terminal.board.cursor.x == 70  # Cursor should remain if within bounds
    assert terminal.board.cursor.y == 20
    assert terminal.board.screen.scroll_bottom == 29  # Should adjust to new height

    terminal.resize(50, 10)
    assert terminal.width == 50
    assert terminal.height == 10
    assert terminal.board.cursor.x == 49  # Cursor should clamp to new width
    assert terminal.board.cursor.y == 9  # Cursor should clamp to new height
    assert terminal.board.screen.scroll_bottom == 9


def test_alternate_terminal_switching():
    terminal = Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    assert not terminal.board.screen.in_alt_screen
    assert terminal.board.screen.current_buffer == terminal.board.screen.primary_buffer

    terminal.board.screen.switch_screen(True)
    assert terminal.board.screen.in_alt_screen
    assert terminal.board.screen.current_buffer == terminal.board.screen.alt_buffer

    # Calling again should do nothing
    terminal.board.screen.switch_screen(True)
    assert terminal.board.screen.in_alt_screen
    assert terminal.board.screen.current_buffer == terminal.board.screen.alt_buffer

    terminal.board.screen.switch_screen(False)
    assert not terminal.board.screen.in_alt_screen
    assert terminal.board.screen.current_buffer == terminal.board.screen.primary_buffer

    # Calling again should do nothing
    terminal.board.screen.switch_screen(False)
    assert not terminal.board.screen.in_alt_screen
    assert terminal.board.screen.current_buffer == terminal.board.screen.primary_buffer


def test_alignment_test():
    terminal = Terminal(width=10, height=5)
    terminal.board.screen.alignment_test()

    expected_char = "E"
    for y in range(terminal.height):
        line_text = terminal.board.screen.current_buffer.get_line_text(y)
        assert len(line_text) == terminal.width
        assert all(char == expected_char for char in line_text)


def test_alternate_terminal_on_off_restores_lines():
    terminal = Terminal(width=10, height=5)
    terminal.board.screen.current_buffer.set(0, 0, "Hello")
    terminal.board.screen.switch_screen(True)
    assert terminal.board.screen.current_buffer.get_line_text(0) == "          "
    terminal.board.screen.switch_screen(False)
    assert terminal.board.screen.current_buffer.get_line_text(0) == "Hello     "


def test_set_and_clear_modes():
    terminal = Terminal(width=80, height=24)

    # Test setting a private mode
    terminal.board.modes.set_mode(DECAWM_AUTOWRAP, private=True)
    assert terminal.board.modes.auto_wrap

    # Test clearing a private mode
    terminal.board.modes.clear_mode(DECAWM_AUTOWRAP, private=True)
    assert not terminal.board.modes.auto_wrap

    # Test setting a non-private mode
    terminal.board.modes.set_mode(IRM_INSERT_REPLACE, private=False)
    assert terminal.board.modes.insert_mode

    # Test clearing a non-private mode
    terminal.board.modes.clear_mode(IRM_INSERT_REPLACE, private=False)
    assert not terminal.board.modes.insert_mode

    # Test an unknown mode
    terminal.board.modes.set_mode(999, private=True)
    # No attribute should be set
    assert not hasattr(terminal, "unknown_mode")
