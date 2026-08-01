"""Test terminal input modes and key translation."""

from bittty import Board, MemoryConnection, constants


def test_cursor_keys_normal_mode():
    """Test cursor keys in normal mode (DECCKM disabled)."""
    board = Board()
    board.pty = MemoryConnection()
    board.modes.cursor_application_mode = False

    # Arrow keys should send ESC[A format
    board.input_key("up")
    assert board.pty.data[-1] == "\x1b[A"

    board.input_key("down")
    assert board.pty.data[-1] == "\x1b[B"


def test_cursor_keys_application_mode():
    """Test cursor keys in application mode (DECCKM enabled)."""
    board = Board()
    board.pty = MemoryConnection()
    board.modes.cursor_application_mode = True

    # Arrow keys should send ESC OA format
    board.input_key("up")
    assert board.pty.data[-1] == "\x1bOA"

    board.input_key("down")
    assert board.pty.data[-1] == "\x1bOB"


def test_cursor_keys_application_mode_translates_input_stream():
    """Raw frontend streams may contain multiple cursor-key sequences."""
    board = Board()
    board.pty = MemoryConnection()
    board.modes.cursor_application_mode = True

    board.input("\x1b[B\x1b[B")

    assert board.pty.data[-1] == "\x1bOB\x1bOB"


def test_cursor_keys_application_mode_translates_embedded_sequence():
    board = Board()
    board.pty = MemoryConnection()
    board.modes.cursor_application_mode = True

    board.input("x\x1b[By")

    assert board.pty.data[-1] == "x\x1bOBy"


def test_modified_cursor_keys():
    """Test cursor keys with modifiers always use CSI format."""
    board = Board()
    board.pty = MemoryConnection()
    board.modes.cursor_application_mode = True  # Even in app mode

    # Modified cursor keys should always use CSI format
    board.input_key("up", constants.KEY_MOD_CTRL)
    assert board.pty.data[-1] == "\x1b[1;5A"


def test_control_characters():
    """Test control character generation."""
    board = Board()
    board.pty = MemoryConnection()

    # Ctrl+A should send \x01
    board.input_key("a", constants.KEY_MOD_CTRL)
    assert board.pty.data[-1] == "\x01"

    # Ctrl+C should send \x03
    board.input_key("c", constants.KEY_MOD_CTRL)
    assert board.pty.data[-1] == "\x03"


def test_function_keys():
    """Test function key generation."""
    board = Board()
    board.pty = MemoryConnection()

    # F1 should send ESC OP
    board.input_fkey(1)
    assert board.pty.data[-1] == "\x1bOP"

    # F5 should send ESC [15~
    board.input_fkey(5)
    assert board.pty.data[-1] == "\x1b[15~"


def test_raw_input_passthrough():
    """Test that raw input passes through unchanged."""
    board = Board()
    board.pty = MemoryConnection()

    # Raw escape sequences should pass through
    board.input("\x1b[3~")  # Delete key
    assert board.pty.data[-1] == "\x1b[3~"

    # Regular characters should pass through
    board.input("hello")
    assert board.pty.data[-1] == "hello"


def test_unhandled_keys_fallback():
    """Test that unhandled keys in input_key() fall back to raw input."""
    board = Board()
    board.pty = MemoryConnection()

    # Backspace character should pass through as fallback
    board.input_key("\x7f")  # DEL character
    assert board.pty.data[-1] == "\x7f"

    # Any other unrecognized character should pass through
    board.input_key("\x1b")  # ESC character
    assert board.pty.data[-1] == "\x1b"
