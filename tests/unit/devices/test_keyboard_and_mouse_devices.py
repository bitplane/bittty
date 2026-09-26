import io

from bittty import Board, MemoryConnection, constants
from bittty.pty import PTY


def board_with_pty():
    board = Board(width=20, height=5)
    board.pty = MemoryConnection()
    return board


def test_keyboard_device_encodes_keys_and_application_cursor_mode():
    board = board_with_pty()

    board.keyboard.input_key("up")
    board.modes.cursor_application_mode = True
    board.keyboard.input_key("down")
    board.keyboard.input_key("a", constants.KEY_MOD_CTRL)

    assert board.pty.data == ["\x1b[A", "\x1bOB", "\x01"]
    assert board.host.connection is board.pty


def test_keyboard_device_encodes_function_and_numpad_keys():
    board = board_with_pty()

    board.keyboard.input_fkey(1)
    board.keyboard.input_fkey(5, constants.KEY_MOD_CTRL)
    board.keyboard.input_numpad_key("5")
    board.modes.numeric_keypad = False
    board.keyboard.input_numpad_key("Enter")

    assert board.pty.data == ["\x1bOP", "\x1b[15;5~", "5", "\x1bOM"]


def test_keyboard_device_backarrow_mode():
    board = board_with_pty()

    board.keyboard.input_key(constants.BS)
    board.modes.backarrow_key_sends_bs = True
    board.keyboard.input_key(constants.BS)

    assert board.pty.data == [constants.DEL, constants.BS]


def test_alt_sends_escape_for_plain_and_control_characters():
    board = board_with_pty()
    board.modes.alt_sends_escape = True

    board.keyboard.input_key("x", constants.KEY_MOD_ALT)
    board.keyboard.input_key("c", constants.KEY_MOD_ALT_CTRL)

    assert board.pty.data == ["\x1bx", "\x1b\x03"]


def test_alt_sends_escape_beats_modify_other_keys_level_one():
    """xterm filterAltMeta: at level 1 an escape-prefixed or bare Alt stays legacy; level 2 reports it."""
    board = board_with_pty()
    board.modes.alt_sends_escape = True
    board.keyboard.modify_other_keys = 1
    board.keyboard.input_key("x", constants.KEY_MOD_ALT)
    board.keyboard.modify_other_keys = 2
    board.keyboard.input_key("x", constants.KEY_MOD_ALT)

    assert board.pty.data == ["\x1bx", "\x1b[27;3;120~"]


def test_meta_can_set_the_eighth_bit_as_a_raw_byte():
    output = io.BytesIO()
    board = Board()
    board.pty = PTY(to_process=output)
    board.modes.eight_bit_input = True

    board.keyboard.input_key("x", constants.KEY_MOD_META)

    assert output.getvalue() == b"\xf8"


def test_meta_sends_escape_takes_precedence_over_eight_bit_input():
    board = board_with_pty()
    board.modes.eight_bit_input = True
    board.modes.meta_sends_escape = True

    board.keyboard.input_key("x", constants.KEY_MOD_META)

    assert board.pty.data == ["\x1bx"]


def test_meta_policy_beats_modify_other_keys_level_one():
    board = board_with_pty()
    board.modes.eight_bit_input = True
    board.modes.meta_sends_escape = True
    board.keyboard.modify_other_keys = 1
    board.keyboard.input_key("x", constants.KEY_MOD_META)
    board.keyboard.modify_other_keys = 2
    board.keyboard.input_key("x", constants.KEY_MOD_META)

    assert board.pty.data == ["\x1bx", "\x1b[27;9;120~"]


def test_alt_on_cursor_keys_stays_a_modifier_parameter():
    """xterm 407: neither mode 1035 nor 1039 turns Alt-Up into an ESC prefix."""
    board = board_with_pty()

    board.keyboard.input_key("up", constants.KEY_MOD_ALT)
    board.modes.special_modifiers = False
    board.keyboard.input_key("up", constants.KEY_MOD_ALT)
    board.modes.alt_sends_escape = True
    board.keyboard.input_key("up", constants.KEY_MOD_ALT)

    assert board.pty.data == ["\x1b[1;3A"] * 3


def test_mouse_device_caches_position_and_gates_tracking():
    board = board_with_pty()
    mouse = board.mouse

    mouse.input_mouse(10, 5, 0, "press", set())
    assert (mouse.x, mouse.y) == (10, 5)
    assert board.pty.data == []

    board.parser.feed("\x1b[?1000h")
    board.parser.feed("\x1b[?1006h")
    mouse.input_mouse(10, 5, 0, "press", {"shift"})

    assert board.pty.data == ["\x1b[<4;10;5M"]


def test_mouse_device_move_requires_any_tracking():
    board = board_with_pty()
    board.parser.feed("\x1b[?1000h")
    board.parser.feed("\x1b[?1006h")

    board.mouse.input_mouse(1, 2, 0, "move", set())
    assert board.pty.data == []

    board.parser.feed("\x1b[?1003h")
    board.mouse.input_mouse(1, 2, 0, "move", set())
    assert board.pty.data == ["\x1b[<35;1;2M"]


def test_mouse_pointer_is_a_register_not_a_composite():
    """The pointer lives in board registers for the chrome to render; video stays pure."""
    board = Board(width=20, height=10)

    board.mouse.show = True
    board.mouse.x = 5
    board.mouse.y = 3

    assert (board.mouse.x, board.mouse.y, board.mouse.show) == (5, 3, True)
    lines = board.capture_pane().split("\n")
    assert lines[2][4] == " "  # nothing composited into video memory


def test_input_mouse_basic():
    """Test basic mouse input functionality."""
    board = Board(width=80, height=24)

    # Enable mouse tracking
    board.parser.feed("\x1b[?1000h")

    # Test mouse press
    board.input_mouse(10, 5, 1, "press", set())

    # Mouse position should be cached
    assert board.mouse.x == 10
    assert board.mouse.y == 5


def test_input_mouse_sgr_mode():
    """Test mouse input with SGR mode."""
    board = Board(width=80, height=24)

    # Enable SGR mouse mode
    board.parser.feed("\x1b[?1006h")
    board.parser.feed("\x1b[?1000h")

    # Test mouse press with modifiers
    modifiers = {"shift", "ctrl"}
    board.input_mouse(15, 8, 1, "press", modifiers)

    # Should handle the input without errors
    assert board.mouse.x == 15
    assert board.mouse.y == 8


def test_input_numpad_key_numeric_mode():
    """Test numpad key input in numeric mode."""
    board = Board(width=80, height=24)

    # Numeric mode (default)
    board.modes.numeric_keypad = True

    # Test numpad keys
    board.input_numpad_key("5")
    board.input_numpad_key(".")
    board.input_numpad_key("Enter")

    # Should complete without errors


def test_input_numpad_key_application_mode():
    """Test numpad key input in application mode."""
    board = Board(width=80, height=24)

    # Application mode
    board.modes.numeric_keypad = False

    # Test numpad keys in application mode
    board.input_numpad_key("0")
    board.input_numpad_key("+")
    board.input_numpad_key("Enter")

    # Should complete without errors


def test_input_fkey():
    """Test function key input."""
    board = Board(width=80, height=24)

    # Test F1-F4 keys
    board.input_fkey(1)  # F1
    board.input_fkey(2)  # F2

    # Test F5-F12 keys
    board.input_fkey(5)  # F5
    board.input_fkey(12)  # F12

    # Test with modifiers
    from bittty.constants import KEY_MOD_CTRL

    board.input_fkey(1, KEY_MOD_CTRL)

    # Should complete without errors


def test_input_key_cursor_keys():
    """Test cursor key input."""
    board = Board(width=80, height=24)

    # Test basic cursor keys
    board.input_key("UP")
    board.input_key("DOWN")
    board.input_key("LEFT")
    board.input_key("RIGHT")

    # Test with modifiers
    from bittty.constants import KEY_MOD_SHIFT

    board.input_key("UP", KEY_MOD_SHIFT)

    # Should complete without errors


def test_input_key_navigation():
    """Test navigation key input."""
    board = Board(width=80, height=24)

    # Test home/end keys
    board.input_key("HOME")
    board.input_key("END")

    # Should complete without errors


def test_input_key_backspace():
    """Test backspace key handling with DECBKM mode."""
    board = Board(width=80, height=24)

    # Test default mode (sends DEL)
    board.modes.backarrow_key_sends_bs = False
    board.input_key("\x08")  # BS character

    # Test DECBKM mode (sends BS)
    board.modes.backarrow_key_sends_bs = True
    board.input_key("\x08")  # BS character

    # Should complete without errors


def test_mouse_device_legacy_encoding_without_sgr():
    """Mode 1000 without 1006 reports in the X10 byte encoding, not silence.

    X10 reports are bytes, not text: the coordinates are 8-bit and a real PTY
    takes them through write_bytes. This asserted str while the old test double
    lacked write_bytes and HostPort fell back to a latin-1 decode — a path no
    real connection takes.
    """
    board = board_with_pty()
    board.parser.feed("\x1b[?1000h")

    board.mouse.input_mouse(10, 5, 0, "press", set())
    assert board.pty.data == [b"\x1b[M" + bytes((32 + 0, 32 + 10, 32 + 5))]

    board.pty.data.clear()
    board.mouse.input_mouse(10, 5, 0, "release", set())
    # A legacy release cannot name its button: low bits are 3.
    assert board.pty.data == [b"\x1b[M" + bytes((32 + 3, 32 + 10, 32 + 5))]


def test_legacy_mouse_uses_raw_bytes_on_a_real_pty_connection():
    output = io.BytesIO()
    board = Board(width=300, height=20)
    board.pty = PTY(to_process=output)
    board.parser.feed("\x1b[?1000h")

    board.mouse.input_mouse(200, 5, 0, "press", set())

    assert output.getvalue() == b"\x1b[M " + bytes((232, 37))


def test_utf8_mouse_encoding_extends_coordinates():
    board = board_with_pty()
    board.parser.feed("\x1b[?1000h")
    board.parser.feed("\x1b[?1005h")

    board.mouse.input_mouse(200, 300, 0, "press", set())

    expected = "\x1b[M" + chr(32) + chr(232) + chr(332)
    assert board.pty.data == [expected]
    assert expected.encode() == b"\x1b[M \xc3\xa8\xc5\x8c"


def test_urxvt_mouse_uses_decimal_parameters_and_x10_button_offset():
    board = board_with_pty()
    board.parser.feed("\x1b[?1000h")
    board.parser.feed("\x1b[?1015h")

    board.mouse.input_mouse(300, 400, 0, "press", set())
    board.mouse.input_mouse(300, 400, 0, "release", set())

    assert board.pty.data == ["\x1b[32;300;400M", "\x1b[35;300;400M"]


def test_sgr_mouse_takes_precedence_over_other_coordinate_encodings():
    board = board_with_pty()
    board.parser.feed("\x1b[?1000h")
    board.parser.feed("\x1b[?1005h")
    board.parser.feed("\x1b[?1015h")
    board.parser.feed("\x1b[?1006h")

    board.mouse.input_mouse(300, 400, 0, "press", set())

    assert board.pty.data == ["\x1b[<0;300;400M"]


def test_alternate_scroll_sends_cursor_keys_only_on_the_alternate_screen():
    board = board_with_pty()
    board.modes.alternate_scroll_mode = True

    board.mouse.input_mouse(5, 5, constants.MOUSE_BUTTON_WHEEL_UP, "press", set())
    board.blitter.switch_screen(True)
    board.mouse.input_mouse(5, 5, constants.MOUSE_BUTTON_WHEEL_UP, "press", set())
    board.mouse.input_mouse(5, 5, constants.MOUSE_BUTTON_WHEEL_DOWN, "press", set())

    assert board.pty.data == ["\x1b[A", "\x1b[B"]


def test_mouse_tracking_takes_precedence_over_alternate_scroll():
    board = board_with_pty()
    board.blitter.switch_screen(True)
    board.modes.alternate_scroll_mode = True
    board.parser.feed("\x1b[?1000h")
    board.parser.feed("\x1b[?1006h")

    board.mouse.input_mouse(5, 5, constants.MOUSE_BUTTON_WHEEL_UP, "press", set())

    assert board.pty.data == ["\x1b[<64;5;5M"]


def test_mouse_device_button_tracking_reports_drag_motion():
    """Mode 1002 reports motion while a button is held (and only then)."""
    board = board_with_pty()
    board.modes.set_private_modes((1002, 1006), True)

    board.mouse.input_mouse(3, 3, 0, "move", set())
    assert board.pty.data == []  # no button held: no report

    board.mouse.input_mouse(3, 3, 0, "press", set())
    board.pty.data.clear()
    board.mouse.input_mouse(4, 3, 0, "move", set())
    assert board.pty.data == ["\x1b[<32;4;3M"]  # motion flag + dragged button 0

    board.mouse.input_mouse(4, 3, 0, "release", set())
    board.pty.data.clear()
    board.mouse.input_mouse(5, 3, 0, "move", set())
    assert board.pty.data == []  # button up again: silence


def test_input_key_modified_tilde_nav_keys():
    """Ctrl+PageUp must encode as ESC[5;5~, not ESC[1;55~."""
    board = board_with_pty()
    board.input_key("pageup", constants.KEY_MOD_CTRL)
    assert board.pty.data == ["\x1b[5;5~"]

    board.pty.data.clear()
    board.input_key("up", constants.KEY_MOD_CTRL)
    assert board.pty.data == ["\x1b[1;5A"]  # letter-final keys keep the 1;mod form


def test_wheel_events_do_not_stick_as_held_buttons():
    """Wheel presses (64/65) have no release; they must not fake a drag."""
    board = board_with_pty()
    board.modes.set_private_modes((1002, 1006), True)

    board.mouse.input_mouse(5, 5, 64, "press", set())  # wheel up
    board.pty.data.clear()
    board.mouse.input_mouse(6, 5, 0, "move", set())
    assert board.pty.data == []  # no button held: still no motion report
