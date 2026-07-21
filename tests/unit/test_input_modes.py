"""Test terminal input modes and key translation."""

from unittest.mock import Mock

from bittty import Board
from bittty import constants


def test_cursor_keys_normal_mode():
    """Test cursor keys in normal mode (DECCKM disabled)."""
    board = Board()
    board.pty = Mock()
    board.modes.cursor_application_mode = False

    # Arrow keys should send ESC[A format
    board.input_key("up")
    board.pty.write.assert_called_with("\x1b[A")

    board.input_key("down")
    board.pty.write.assert_called_with("\x1b[B")


def test_cursor_keys_application_mode():
    """Test cursor keys in application mode (DECCKM enabled)."""
    board = Board()
    board.pty = Mock()
    board.modes.cursor_application_mode = True

    # Arrow keys should send ESC OA format
    board.input_key("up")
    board.pty.write.assert_called_with("\x1bOA")

    board.input_key("down")
    board.pty.write.assert_called_with("\x1bOB")


def test_modified_cursor_keys():
    """Test cursor keys with modifiers always use CSI format."""
    board = Board()
    board.pty = Mock()
    board.modes.cursor_application_mode = True  # Even in app mode

    # Modified cursor keys should always use CSI format
    board.input_key("up", constants.KEY_MOD_CTRL)
    board.pty.write.assert_called_with("\x1b[1;5A")


def test_control_characters():
    """Test control character generation."""
    board = Board()
    board.pty = Mock()

    # Ctrl+A should send \x01
    board.input_key("a", constants.KEY_MOD_CTRL)
    board.pty.write.assert_called_with("\x01")

    # Ctrl+C should send \x03
    board.input_key("c", constants.KEY_MOD_CTRL)
    board.pty.write.assert_called_with("\x03")


def test_function_keys():
    """Test function key generation."""
    board = Board()
    board.pty = Mock()

    # F1 should send ESC OP
    board.input_fkey(1)
    board.pty.write.assert_called_with("\x1bOP")

    # F5 should send ESC [15~
    board.input_fkey(5)
    board.pty.write.assert_called_with("\x1b[15~")


def test_raw_input_passthrough():
    """Test that raw input passes through unchanged."""
    board = Board()
    board.pty = Mock()

    # Raw escape sequences should pass through
    board.input("\x1b[3~")  # Delete key
    board.pty.write.assert_called_with("\x1b[3~")

    # Regular characters should pass through
    board.input("hello")
    board.pty.write.assert_called_with("hello")


def test_unhandled_keys_fallback():
    """Test that unhandled keys in input_key() fall back to raw input."""
    board = Board()
    board.pty = Mock()

    # Backspace character should pass through as fallback
    board.input_key("\x7f")  # DEL character
    board.pty.write.assert_called_with("\x7f")

    # Any other unrecognized character should pass through
    board.input_key("\x1b")  # ESC character
    board.pty.write.assert_called_with("\x1b")


class _RecordingTransport:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data.append(data)

    def flush(self):
        pass


def test_paste_is_raw_without_bracketed_mode():
    board = Board()
    transport = _RecordingTransport()
    board.host.attach(transport)
    board.input_paste("hello\nworld")
    assert transport.data == ["hello\nworld"]


def test_paste_is_bracketed_when_2004_is_on():
    board = Board()
    transport = _RecordingTransport()
    board.host.attach(transport)
    board.modes.bracketed_paste = True
    board.input_paste("hello")
    assert transport.data == ["\x1b[200~hello\x1b[201~"]


def test_display_port_forwards_paste():
    board = Board()
    transport = _RecordingTransport()
    board.host.attach(transport)
    board.display.input_paste("x")
    assert transport.data == ["x"]
