from bittty.terminal import Terminal


def test_show_mouse_cursor():
    """Test that the mouse cursor is rendered when show_mouse is True."""
    # Create a terminal
    terminal = Terminal(width=20, height=10)

    # Enable the mouse cursor
    terminal.show_mouse = True

    # Set a mouse position
    terminal.mouse_x = 5
    terminal.mouse_y = 3

    # Get the content and check for the cursor
    content = terminal.capture_pane()
    # The mouse cursor is at (5,3), which is index 4 of line 2 (0-indexed)
    # The capture_pane output includes newlines, so we need to split it.
    lines = content.split("\n")
    assert lines[2][4] == "↖"

    # Disable the mouse cursor
    terminal.show_mouse = False

    # Get the content and check that the cursor is gone
    content = terminal.capture_pane()
    lines = content.split("\n")
    assert lines[2][4] != "↖"


def test_input_mouse_basic():
    """Test basic mouse input functionality."""
    terminal = Terminal(width=80, height=24)

    # Enable mouse tracking
    terminal.mouse_tracking = True

    # Test mouse press
    terminal.input_mouse(10, 5, 1, "press", set())

    # Mouse position should be cached
    assert terminal.mouse_x == 10
    assert terminal.mouse_y == 5


def test_input_mouse_sgr_mode():
    """Test mouse input with SGR mode."""
    terminal = Terminal(width=80, height=24)

    # Enable SGR mouse mode
    terminal.mouse_sgr_mode = True
    terminal.mouse_tracking = True

    # Test mouse press with modifiers
    modifiers = {"shift", "ctrl"}
    terminal.input_mouse(15, 8, 1, "press", modifiers)

    # Should handle the input without errors
    assert terminal.mouse_x == 15
    assert terminal.mouse_y == 8


def test_input_numpad_key_numeric_mode():
    """Test numpad key input in numeric mode."""
    terminal = Terminal(width=80, height=24)

    # Numeric mode (default)
    terminal.numeric_keypad = True

    # Test numpad keys
    terminal.input_numpad_key("5")
    terminal.input_numpad_key(".")
    terminal.input_numpad_key("Enter")

    # Should complete without errors


def test_input_numpad_key_application_mode():
    """Test numpad key input in application mode."""
    terminal = Terminal(width=80, height=24)

    # Application mode
    terminal.numeric_keypad = False

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
    terminal.backarrow_key_sends_bs = False
    terminal.input_key("\x08")  # BS character

    # Test DECBKM mode (sends BS)
    terminal.backarrow_key_sends_bs = True
    terminal.input_key("\x08")  # BS character

    # Should complete without errors
