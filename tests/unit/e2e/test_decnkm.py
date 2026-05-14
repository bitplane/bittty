"""Test DECNKM (Numeric-Keypad Mode) implementation."""

from bittty.terminal import Terminal
from bittty.parser import Parser


def test_decnkm_default_numeric_mode():
    """Test that keypad is in numeric mode by default."""
    terminal = Terminal(width=20, height=5)

    # Should be in numeric mode by default (numeric_keypad = True)
    assert terminal.numeric_keypad


def test_decnkm_set_application_mode():
    """Test setting DECNKM to application keypad mode."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set DECNKM application mode (ESC [ ? 66 h)
    parser.feed("\x1b[?66h")

    # Should enable application keypad mode
    assert not terminal.numeric_keypad


def test_decnkm_reset_to_numeric():
    """Test resetting DECNKM back to numeric mode."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Set application mode first
    parser.feed("\x1b[?66h")
    assert not terminal.numeric_keypad

    # Reset DECNKM mode (ESC [ ? 66 l)
    parser.feed("\x1b[?66l")

    # Should return to numeric mode
    assert terminal.numeric_keypad


def test_decnkm_affects_numpad_keys():
    """Test that DECNKM affects how numpad keys are sent."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # Mock the PTY to capture output
    sent_data = []

    class MockPTY:
        def write(self, data):
            sent_data.append(data)

    terminal.pty = MockPTY()

    # Test numeric mode (default)
    terminal.input_numpad_key("0")
    assert sent_data == ["0"]

    sent_data.clear()

    # Switch to application mode
    parser.feed("\x1b[?66h")

    # Same key should now send application sequence
    terminal.input_numpad_key("0")
    assert sent_data == ["\x1bOp"]  # Application mode for 0


def test_decnkm_all_numpad_keys():
    """Test all numpad keys in both modes."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    sent_data = []

    class MockPTY:
        def write(self, data):
            sent_data.append(data)

    terminal.pty = MockPTY()

    # Test in numeric mode
    numeric_keys = {
        "0": "0",
        "1": "1",
        "2": "2",
        "3": "3",
        "4": "4",
        "5": "5",
        "6": "6",
        "7": "7",
        "8": "8",
        "9": "9",
        ".": ".",
        "+": "+",
        "-": "-",
        "*": "*",
        "/": "/",
        "Enter": "\r",
    }

    for key, expected in numeric_keys.items():
        sent_data.clear()
        terminal.input_numpad_key(key)
        assert sent_data == [expected], f"Numeric mode: {key} should send {expected!r}"

    # Switch to application mode
    parser.feed("\x1b[?66h")

    # Test in application mode
    app_keys = {
        "0": "\x1bOp",
        "1": "\x1bOq",
        "2": "\x1bOr",
        "3": "\x1bOs",
        "4": "\x1bOt",
        "5": "\x1bOu",
        "6": "\x1bOv",
        "7": "\x1bOw",
        "8": "\x1bOx",
        "9": "\x1bOy",
        ".": "\x1bOn",
        "+": "\x1bOk",
        "-": "\x1bOm",
        "*": "\x1bOj",
        "/": "\x1bOo",
        "Enter": "\x1bOM",
    }

    for key, expected in app_keys.items():
        sent_data.clear()
        terminal.input_numpad_key(key)
        assert sent_data == [expected], f"Application mode: {key} should send {expected!r}"


def test_decnkm_escape_sequences():
    """Test that DECNKM responds to both ESC = and ESC > sequences."""
    terminal = Terminal(width=20, height=5)
    parser = Parser(terminal)

    # ESC = should set application mode (same as CSI ? 66 h)
    parser.feed("\x1b=")
    assert not terminal.numeric_keypad

    # ESC > should set numeric mode (same as CSI ? 66 l)
    parser.feed("\x1b>")
    assert terminal.numeric_keypad
