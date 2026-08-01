from bittty import Board
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT, DECAWM_AUTOWRAP, IRM_INSERT_REPLACE


def test_resize():
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    board.cursor.x = 70
    board.cursor.y = 20

    board.resize(100, 30)
    assert board.width == 100
    assert board.height == 30
    assert board.cursor.x == 70  # Cursor should remain if within bounds
    assert board.cursor.y == 20
    assert board.blitter.scroll_bottom == 29  # Should adjust to new height

    board.resize(50, 10)
    assert board.width == 50
    assert board.height == 10
    assert board.cursor.x == 49  # Cursor should clamp to new width
    assert board.cursor.y == 9  # Cursor should clamp to new height
    assert board.blitter.scroll_bottom == 9


def test_alternate_screen_switching():
    board = Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)
    assert not board.blitter.in_alt_screen
    assert board.blitter.current_page == board.blitter.primary_page

    board.blitter.switch_screen(True)
    assert board.blitter.in_alt_screen
    assert board.blitter.current_page == board.blitter.alt_page

    # Calling again should do nothing
    board.blitter.switch_screen(True)
    assert board.blitter.in_alt_screen
    assert board.blitter.current_page == board.blitter.alt_page

    board.blitter.switch_screen(False)
    assert not board.blitter.in_alt_screen
    assert board.blitter.current_page == board.blitter.primary_page

    # Calling again should do nothing
    board.blitter.switch_screen(False)
    assert not board.blitter.in_alt_screen
    assert board.blitter.current_page == board.blitter.primary_page


def test_alignment_test():
    board = Board(width=10, height=5)
    board.blitter.alignment_test()

    expected_char = "E"
    for y in range(board.height):
        line_text = board.blitter.current_page.get_line_text(y)
        assert len(line_text) == board.width
        assert all(char == expected_char for char in line_text)


def test_alternate_screen_on_off_restores_lines():
    board = Board(width=10, height=5)
    board.blitter.current_page.set(0, 0, "Hello")
    board.blitter.switch_screen(True)
    assert board.blitter.current_page.get_line_text(0) == "          "
    board.blitter.switch_screen(False)
    assert board.blitter.current_page.get_line_text(0) == "Hello     "


def test_set_and_clear_modes():
    board = Board(width=80, height=24)

    # Test setting a private mode
    board.modes.set_mode(DECAWM_AUTOWRAP, private=True)
    assert board.modes.auto_wrap

    # Test clearing a private mode
    board.modes.clear_mode(DECAWM_AUTOWRAP, private=True)
    assert not board.modes.auto_wrap

    # Test setting a non-private mode
    board.modes.set_mode(IRM_INSERT_REPLACE, private=False)
    assert board.modes.insert_mode

    # Test clearing a non-private mode
    board.modes.clear_mode(IRM_INSERT_REPLACE, private=False)
    assert not board.modes.insert_mode

    # Test an unknown mode
    board.modes.set_mode(999, private=True)
    # No attribute should be set
    assert not hasattr(board, "unknown_mode")
