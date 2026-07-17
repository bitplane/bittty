"""Test DECBKM (Backarrow-Key Mode) implementation."""

from bittty import Board
from bittty.parser import Parser
from bittty import constants


def test_decbkm_default_mode():
    """Test that backspace sends DEL by default."""
    terminal = Board(width=20, height=5)

    # Mock the PTY to capture output
    sent_data = []

    class MockPTY:
        def write(self, data):
            sent_data.append(data)

    terminal.pty = MockPTY()

    # Send backspace key
    terminal.input_key(constants.BS, constants.KEY_MOD_NONE)

    # Should send DEL (0x7F) by default
    assert sent_data == ["\x7f"]


def test_decbkm_set_bs_mode():
    """Test setting DECBKM to send BS instead of DEL."""
    terminal = Board(width=20, height=5)
    parser = Parser(terminal.board)

    # Mock the PTY to capture output
    sent_data = []

    class MockPTY:
        def write(self, data):
            sent_data.append(data)

    terminal.pty = MockPTY()

    # Set DECBKM mode (ESC [ ? 67 h)
    parser.feed("\x1b[?67h")

    # Send backspace key
    terminal.input_key(constants.BS, constants.KEY_MOD_NONE)

    # Should send BS (0x08) when mode is set
    assert sent_data == ["\x08"]


def test_decbkm_reset_to_del():
    """Test resetting DECBKM back to DEL mode."""
    terminal = Board(width=20, height=5)
    parser = Parser(terminal.board)

    # Mock the PTY to capture output
    sent_data = []

    class MockPTY:
        def write(self, data):
            sent_data.append(data)

    terminal.pty = MockPTY()

    # Set DECBKM mode first
    parser.feed("\x1b[?67h")

    # Reset DECBKM mode (ESC [ ? 67 l)
    parser.feed("\x1b[?67l")

    # Send backspace key
    terminal.input_key(constants.BS, constants.KEY_MOD_NONE)

    # Should send DEL (0x7F) when mode is reset
    assert sent_data == ["\x7f"]
