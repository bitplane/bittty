from bittty.terminal import Terminal


def test_cursor_device_owns_position_and_save_restore():
    terminal = Terminal(width=10, height=5)
    cursor = terminal.cursor

    cursor.set_position(4, 2)
    terminal.current_ansi_code = "\x1b[31m"
    cursor.save()

    cursor.set_position(9, 4)
    terminal.current_ansi_code = "\x1b[32m"
    cursor.restore()

    assert (cursor.x, cursor.y) == (4, 2)
    assert terminal.current_ansi_code == "\x1b[31m"


def test_cursor_device_tabs_and_basic_movement():
    terminal = Terminal(width=12, height=5)
    cursor = terminal.cursor

    cursor.set_position(3, 2)
    cursor.set_tab_stop()
    cursor.set_position(0, 2)
    cursor.horizontal_tab()
    assert cursor.x == 3

    cursor.move_forward(20)
    assert cursor.x == 11
    cursor.move_back(20)
    assert cursor.x == 0
    cursor.move_up(20)
    assert cursor.y == 0
    cursor.move_down(20)
    assert cursor.y == 4


def test_cursor_device_line_feed_scrolls_screen_region():
    terminal = Terminal(width=8, height=3)
    terminal.screen.current_buffer.set(0, 0, "top")
    terminal.screen.current_buffer.set(0, 1, "mid")
    terminal.screen.current_buffer.set(0, 2, "bot")

    terminal.cursor.set_position(0, 2)
    terminal.cursor.line_feed()

    assert terminal.cursor.y == 2
    assert terminal.screen.current_buffer.get_line_text(0).startswith("mid")
    assert terminal.screen.current_buffer.get_line_text(1).startswith("bot")


def test_cursor_device_text_write_wrap_preparation():
    terminal = Terminal(width=4, height=3)
    cursor = terminal.cursor

    cursor.x = 4
    cursor.y = 0
    cursor.prepare_for_text_write()

    assert (cursor.x, cursor.y) == (0, 1)
