from bittty import constants
from bittty.terminal import Terminal


class RecordingPTY:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def terminal_with_pty():
    terminal = Terminal(width=20, height=5)
    terminal.pty = RecordingPTY()
    return terminal


def test_keyboard_device_encodes_keys_and_application_cursor_mode():
    terminal = terminal_with_pty()

    terminal.board.keyboard.input_key("up")
    terminal.board.modes.cursor_application_mode = True
    terminal.board.keyboard.input_key("down")
    terminal.board.keyboard.input_key("a", constants.KEY_MOD_CTRL)

    assert terminal.pty.data == ["\x1b[A", "\x1bOB", "\x01"]
    assert terminal.board.host.transport is terminal.pty


def test_keyboard_device_encodes_function_and_numpad_keys():
    terminal = terminal_with_pty()

    terminal.board.keyboard.input_fkey(1)
    terminal.board.keyboard.input_fkey(5, constants.KEY_MOD_CTRL)
    terminal.board.keyboard.input_numpad_key("5")
    terminal.board.modes.numeric_keypad = False
    terminal.board.keyboard.input_numpad_key("Enter")

    assert terminal.pty.data == ["\x1bOP", "\x1b[15;5~", "5", "\x1bOM"]


def test_keyboard_device_backarrow_mode():
    terminal = terminal_with_pty()

    terminal.board.keyboard.input_key(constants.BS)
    terminal.board.modes.backarrow_key_sends_bs = True
    terminal.board.keyboard.input_key(constants.BS)

    assert terminal.pty.data == [constants.DEL, constants.BS]


def test_mouse_device_caches_position_and_gates_tracking():
    terminal = terminal_with_pty()
    mouse = terminal.board.mouse

    mouse.input_mouse(10, 5, 0, "press", set())
    assert (mouse.x, mouse.y) == (10, 5)
    assert terminal.pty.data == []

    terminal.board.modes.mouse_tracking = True
    terminal.board.modes.mouse_sgr_mode = True
    mouse.input_mouse(10, 5, 0, "press", {"shift"})

    assert terminal.pty.data == ["\x1b[<4;10;5M"]


def test_mouse_device_move_requires_any_tracking():
    terminal = terminal_with_pty()
    terminal.board.modes.mouse_tracking = True
    terminal.board.modes.mouse_sgr_mode = True

    terminal.board.mouse.input_mouse(1, 2, 0, "move", set())
    assert terminal.pty.data == []

    terminal.board.modes.mouse_any_tracking = True
    terminal.board.mouse.input_mouse(1, 2, 0, "move", set())
    assert terminal.pty.data == ["\x1b[<35;1;2M"]


def test_show_mouse_cursor():
    """Test that the mouse cursor is rendered when show_mouse is True."""
    # Create a terminal
    terminal = Terminal(width=20, height=10)

    # Enable the mouse cursor
    terminal.board.mouse.show = True

    # Set a mouse position
    terminal.board.mouse.x = 5
    terminal.board.mouse.y = 3

    # Get the content and check for the cursor
    content = terminal.capture_pane()
    # The mouse cursor is at (5,3), which is index 4 of line 2 (0-indexed)
    # The capture_pane output includes newlines, so we need to split it.
    lines = content.split("\n")
    assert lines[2][4] == "↖"

    # Disable the mouse cursor
    terminal.board.mouse.show = False

    # Get the content and check that the cursor is gone
    content = terminal.capture_pane()
    lines = content.split("\n")
    assert lines[2][4] != "↖"


def test_input_mouse_basic():
    """Test basic mouse input functionality."""
    terminal = Terminal(width=80, height=24)

    # Enable mouse tracking
    terminal.board.modes.mouse_tracking = True

    # Test mouse press
    terminal.input_mouse(10, 5, 1, "press", set())

    # Mouse position should be cached
    assert terminal.board.mouse.x == 10
    assert terminal.board.mouse.y == 5


def test_input_mouse_sgr_mode():
    """Test mouse input with SGR mode."""
    terminal = Terminal(width=80, height=24)

    # Enable SGR mouse mode
    terminal.board.modes.mouse_sgr_mode = True
    terminal.board.modes.mouse_tracking = True

    # Test mouse press with modifiers
    modifiers = {"shift", "ctrl"}
    terminal.input_mouse(15, 8, 1, "press", modifiers)

    # Should handle the input without errors
    assert terminal.board.mouse.x == 15
    assert terminal.board.mouse.y == 8


def test_input_numpad_key_numeric_mode():
    """Test numpad key input in numeric mode."""
    terminal = Terminal(width=80, height=24)

    # Numeric mode (default)
    terminal.board.modes.numeric_keypad = True

    # Test numpad keys
    terminal.input_numpad_key("5")
    terminal.input_numpad_key(".")
    terminal.input_numpad_key("Enter")

    # Should complete without errors


def test_input_numpad_key_application_mode():
    """Test numpad key input in application mode."""
    terminal = Terminal(width=80, height=24)

    # Application mode
    terminal.board.modes.numeric_keypad = False

    # Test numpad keys in application mode
    terminal.input_numpad_key("0")
    terminal.input_numpad_key("+")
    terminal.input_numpad_key("Enter")

    # Should complete without errors


def test_input_fkey():
    """Test function key input."""
    terminal = Terminal(width=80, height=24)

    # Test F1-F4 keys
    terminal.input_fkey(1)  # F1
    terminal.input_fkey(2)  # F2

    # Test F5-F12 keys
    terminal.input_fkey(5)  # F5
    terminal.input_fkey(12)  # F12

    # Test with modifiers
    from bittty.constants import KEY_MOD_CTRL

    terminal.input_fkey(1, KEY_MOD_CTRL)

    # Should complete without errors


def test_input_key_cursor_keys():
    """Test cursor key input."""
    terminal = Terminal(width=80, height=24)

    # Test basic cursor keys
    terminal.input_key("UP")
    terminal.input_key("DOWN")
    terminal.input_key("LEFT")
    terminal.input_key("RIGHT")

    # Test with modifiers
    from bittty.constants import KEY_MOD_SHIFT

    terminal.input_key("UP", KEY_MOD_SHIFT)

    # Should complete without errors


def test_input_key_navigation():
    """Test navigation key input."""
    terminal = Terminal(width=80, height=24)

    # Test home/end keys
    terminal.input_key("HOME")
    terminal.input_key("END")

    # Should complete without errors


def test_input_key_backspace():
    """Test backspace key handling with DECBKM mode."""
    terminal = Terminal(width=80, height=24)

    # Test default mode (sends DEL)
    terminal.board.modes.backarrow_key_sends_bs = False
    terminal.input_key("\x08")  # BS character

    # Test DECBKM mode (sends BS)
    terminal.board.modes.backarrow_key_sends_bs = True
    terminal.input_key("\x08")  # BS character

    # Should complete without errors


def test_mouse_device_legacy_encoding_without_sgr():
    """Mode 1000 without 1006 reports in the X10 byte encoding, not silence."""
    terminal = terminal_with_pty()
    terminal.board.modes.mouse_tracking = True

    terminal.board.mouse.input_mouse(10, 5, 0, "press", set())
    assert terminal.pty.data == ["\x1b[M" + chr(32 + 0) + chr(32 + 10) + chr(32 + 5)]

    terminal.pty.data.clear()
    terminal.board.mouse.input_mouse(10, 5, 0, "release", set())
    # A legacy release cannot name its button: low bits are 3.
    assert terminal.pty.data == ["\x1b[M" + chr(32 + 3) + chr(32 + 10) + chr(32 + 5)]


def test_mouse_device_button_tracking_reports_drag_motion():
    """Mode 1002 reports motion while a button is held (and only then)."""
    terminal = terminal_with_pty()
    terminal.board.modes.set_private_modes((1002, 1006), True)

    terminal.board.mouse.input_mouse(3, 3, 0, "move", set())
    assert terminal.pty.data == []  # no button held: no report

    terminal.board.mouse.input_mouse(3, 3, 0, "press", set())
    terminal.pty.data.clear()
    terminal.board.mouse.input_mouse(4, 3, 0, "move", set())
    assert terminal.pty.data == ["\x1b[<32;4;3M"]  # motion flag + dragged button 0

    terminal.board.mouse.input_mouse(4, 3, 0, "release", set())
    terminal.pty.data.clear()
    terminal.board.mouse.input_mouse(5, 3, 0, "move", set())
    assert terminal.pty.data == []  # button up again: silence


def test_input_key_modified_tilde_nav_keys():
    """Ctrl+PageUp must encode as ESC[5;5~, not ESC[1;55~."""
    terminal = terminal_with_pty()
    terminal.input_key("pageup", constants.KEY_MOD_CTRL)
    assert terminal.pty.data == ["\x1b[5;5~"]

    terminal.pty.data.clear()
    terminal.input_key("up", constants.KEY_MOD_CTRL)
    assert terminal.pty.data == ["\x1b[1;5A"]  # letter-final keys keep the 1;mod form


def test_wheel_events_do_not_stick_as_held_buttons():
    """Wheel presses (64/65) have no release; they must not fake a drag."""
    terminal = terminal_with_pty()
    terminal.board.modes.set_private_modes((1002, 1006), True)

    terminal.board.mouse.input_mouse(5, 5, 64, "press", set())  # wheel up
    terminal.pty.data.clear()
    terminal.board.mouse.input_mouse(6, 5, 0, "move", set())
    assert terminal.pty.data == []  # no button held: still no motion report
