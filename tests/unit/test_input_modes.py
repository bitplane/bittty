"""Test terminal input modes and key translation."""

from unittest.mock import Mock

from bittty.terminal import Terminal
from bittty import constants


def test_cursor_keys_normal_mode():
    """Test cursor keys in normal mode (DECCKM disabled)."""
    terminal = Terminal()
    terminal.pty = Mock()
    terminal.cursor_application_mode = False

    # Arrow keys should send ESC[A format
    terminal.input_key("up")
    terminal.pty.write.assert_called_with("\x1b[A")

    terminal.input_key("down")
    terminal.pty.write.assert_called_with("\x1b[B")


def test_cursor_keys_application_mode():
    """Test cursor keys in application mode (DECCKM enabled)."""
    terminal = Terminal()
    terminal.pty = Mock()
    terminal.cursor_application_mode = True

    # Arrow keys should send ESC OA format
    terminal.input_key("up")
    terminal.pty.write.assert_called_with("\x1bOA")

    terminal.input_key("down")
    terminal.pty.write.assert_called_with("\x1bOB")


def test_modified_cursor_keys():
    """Test cursor keys with modifiers always use CSI format."""
    terminal = Terminal()
    terminal.pty = Mock()
    terminal.cursor_application_mode = True  # Even in app mode

    # Modified cursor keys should always use CSI format
    terminal.input_key("up", constants.KEY_MOD_CTRL)
    terminal.pty.write.assert_called_with("\x1b[1;5A")


def test_control_characters():
    """Test control character generation."""
    terminal = Terminal()
    terminal.pty = Mock()

    # Ctrl+A should send \x01
    terminal.input_key("a", constants.KEY_MOD_CTRL)
    terminal.pty.write.assert_called_with("\x01")

    # Ctrl+C should send \x03
    terminal.input_key("c", constants.KEY_MOD_CTRL)
    terminal.pty.write.assert_called_with("\x03")


def test_function_keys():
    """Test function key generation."""
    terminal = Terminal()
    terminal.pty = Mock()

    # F1 should send ESC OP
    terminal.input_fkey(1)
    terminal.pty.write.assert_called_with("\x1bOP")

    # F5 should send ESC [15~
    terminal.input_fkey(5)
    terminal.pty.write.assert_called_with("\x1b[15~")


def test_raw_input_passthrough():
    """Test that raw input passes through unchanged."""
    terminal = Terminal()
    terminal.pty = Mock()

    # Raw escape sequences should pass through
    terminal.input("\x1b[3~")  # Delete key
    terminal.pty.write.assert_called_with("\x1b[3~")

    # Regular characters should pass through
    terminal.input("hello")
    terminal.pty.write.assert_called_with("hello")


def test_unhandled_keys_fallback():
    """Test that unhandled keys in input_key() fall back to raw input."""
    terminal = Terminal()
    terminal.pty = Mock()

    # Backspace character should pass through as fallback
    terminal.input_key("\x7f")  # DEL character
    terminal.pty.write.assert_called_with("\x7f")

    # Any other unrecognized character should pass through
    terminal.input_key("\x1b")  # ESC character
    terminal.pty.write.assert_called_with("\x1b")
