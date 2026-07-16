from bittty import constants
from bittty.operations import Operation
from bittty.terminal import Terminal


def test_mode_device_owns_ansi_and_private_mode_state():
    terminal = Terminal(width=80, height=24)
    modes = terminal.board.modes

    modes.set_ansi_modes((4, 7, 12, 20), True)
    assert modes.insert_mode is True
    assert modes.auto_wrap is True
    assert modes.local_echo is False
    assert modes.linefeed_newline_mode is True

    modes.set_private_modes((1, 5, 8, 1000, 1006, 2004), True)
    assert modes.cursor_application_mode is True
    assert modes.reverse_screen is True
    assert modes.auto_repeat is True
    assert modes.mouse_tracking is True
    assert modes.mouse_sgr_mode is True
    assert modes.bracketed_paste is True


def test_mode_device_reports_query_status_from_its_state():
    terminal = Terminal(width=80, height=24)
    modes = terminal.board.modes

    modes.insert_mode = True
    modes.auto_wrap = False
    modes.cursor_visible = False

    assert modes.get_ansi_mode_status(4) == 1
    assert modes.get_ansi_mode_status(7) == 2
    assert modes.get_private_mode_status(25) == 2


def test_mode_device_keypad_operations_and_side_effects():
    terminal = Terminal(width=80, height=24)
    modes = terminal.board.modes

    modes.handle_operation(Operation("mode", "DECKPAM", raw="\x1b="))
    assert modes.application_keypad is True
    assert modes.numeric_keypad is False

    modes.handle_operation(Operation("mode", "DECKPNM", raw="\x1b>"))
    assert modes.application_keypad is False
    assert modes.numeric_keypad is True

    modes.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, True)
    assert modes.application_keypad is True


def test_mode_device_alt_screen_and_save_restore_side_effects():
    terminal = Terminal(width=80, height=24)
    terminal.board.cursor.set_position(3, 4)

    terminal.board.modes.set_private_modes((1049,), True)
    assert terminal.board.screen.in_alt_screen is True

    terminal.board.cursor.set_position(9, 9)
    terminal.board.modes.set_private_modes((1049,), False)

    assert terminal.board.screen.in_alt_screen is False
    assert (terminal.board.cursor.x, terminal.board.cursor.y) == (3, 4)
