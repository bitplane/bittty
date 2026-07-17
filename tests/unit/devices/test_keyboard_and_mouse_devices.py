from bittty import constants
from bittty import Board


class RecordingPTY:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def board_with_pty():
    board = Board(width=20, height=5)
    board.pty = RecordingPTY()
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


def test_mouse_device_caches_position_and_gates_tracking():
    board = board_with_pty()
    mouse = board.mouse

    mouse.input_mouse(10, 5, 0, "press", set())
    assert (mouse.x, mouse.y) == (10, 5)
    assert board.pty.data == []

    board.modes.mouse_tracking = True
    board.modes.mouse_sgr_mode = True
    mouse.input_mouse(10, 5, 0, "press", {"shift"})

    assert board.pty.data == ["\x1b[<4;10;5M"]


def test_mouse_device_move_requires_any_tracking():
    board = board_with_pty()
    board.modes.mouse_tracking = True
    board.modes.mouse_sgr_mode = True

    board.mouse.input_mouse(1, 2, 0, "move", set())
    assert board.pty.data == []

    board.modes.mouse_any_tracking = True
    board.mouse.input_mouse(1, 2, 0, "move", set())
    assert board.pty.data == ["\x1b[<35;1;2M"]


def test_show_mouse_cursor():
    """Test that the mouse cursor is rendered when show_mouse is True."""
    # Create a terminal
    board = Board(width=20, height=10)

    # Enable the mouse cursor
    board.mouse.show = True

    # Set a mouse position
    board.mouse.x = 5
    board.mouse.y = 3

    # Get the content and check for the cursor
    content = board.capture_pane()
    # The mouse cursor is at (5,3), which is index 4 of line 2 (0-indexed)
    # The capture_pane output includes newlines, so we need to split it.
    lines = content.split("\n")
    assert lines[2][4] == "↖"

    # Disable the mouse cursor
    board.mouse.show = False

    # Get the content and check that the cursor is gone
    content = board.capture_pane()
    lines = content.split("\n")
    assert lines[2][4] != "↖"


def test_input_mouse_basic():
    """Test basic mouse input functionality."""
    board = Board(width=80, height=24)

    # Enable mouse tracking
    board.modes.mouse_tracking = True

    # Test mouse press
    board.input_mouse(10, 5, 1, "press", set())

    # Mouse position should be cached
    assert board.mouse.x == 10
    assert board.mouse.y == 5


def test_input_mouse_sgr_mode():
    """Test mouse input with SGR mode."""
    board = Board(width=80, height=24)

    # Enable SGR mouse mode
    board.modes.mouse_sgr_mode = True
    board.modes.mouse_tracking = True

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
    """Mode 1000 without 1006 reports in the X10 byte encoding, not silence."""
    board = board_with_pty()
    board.modes.mouse_tracking = True

    board.mouse.input_mouse(10, 5, 0, "press", set())
    assert board.pty.data == ["\x1b[M" + chr(32 + 0) + chr(32 + 10) + chr(32 + 5)]

    board.pty.data.clear()
    board.mouse.input_mouse(10, 5, 0, "release", set())
    # A legacy release cannot name its button: low bits are 3.
    assert board.pty.data == ["\x1b[M" + chr(32 + 3) + chr(32 + 10) + chr(32 + 5)]


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
