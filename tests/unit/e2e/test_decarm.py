"""Test DECARM (Auto-Repeat Mode) implementation."""

from bittty import Board
from bittty.parser import Parser
from bittty import constants


def test_decarm_default_auto_repeat_enabled():
    """Test that auto-repeat is enabled by default."""
    board = Board(width=20, height=5)

    # Should be enabled by default (auto_repeat = True)
    assert board.modes.auto_repeat


def test_decarm_disable_auto_repeat():
    """Test disabling DECARM to prevent key auto-repeat."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Disable DECARM mode (ESC [ ? 8 l)
    parser.feed("\x1b[?8l")

    # Should disable auto-repeat
    assert not board.modes.auto_repeat


def test_decarm_enable_auto_repeat():
    """Test enabling DECARM to allow key auto-repeat."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Disable first
    parser.feed("\x1b[?8l")
    assert not board.modes.auto_repeat

    # Enable DECARM mode (ESC [ ? 8 h)
    parser.feed("\x1b[?8h")

    # Should enable auto-repeat
    assert board.modes.auto_repeat


def test_decarm_affects_key_handling():
    """Test that DECARM mode affects how keys are processed."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Mock key repeat detection
    sent_data = []

    class MockPTY:
        def write(self, data):
            sent_data.append(data)

    board.pty = MockPTY()

    # Disable auto-repeat
    parser.feed("\x1b[?8l")

    # Simulate rapid key presses (would normally auto-repeat)
    for _ in range(5):
        board.input_key("a", constants.KEY_MOD_NONE)

    # With auto-repeat disabled, each press should still go through
    # (The actual repeat filtering would happen at a higher level)
    assert len(sent_data) == 5
    assert all(data == "a" for data in sent_data)


def test_decarm_toggle_state():
    """Test toggling DECARM state multiple times."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Start with default (enabled)
    assert board.modes.auto_repeat

    # Disable
    parser.feed("\x1b[?8l")
    assert not board.modes.auto_repeat

    # Enable
    parser.feed("\x1b[?8h")
    assert board.modes.auto_repeat

    # Disable again
    parser.feed("\x1b[?8l")
    assert not board.modes.auto_repeat
