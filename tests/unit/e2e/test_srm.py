"""Test SRM (Send/Receive Mode) implementation."""

from bittty import Board
from bittty.parser import Parser


def test_srm_default_echo_enabled():
    """Test that local echo is enabled by default."""
    board = Board(width=20, height=5)

    # Should have local echo enabled by default (local_echo = True)
    assert board.modes.local_echo


def test_srm_disable_local_echo():
    """Test disabling SRM to turn off local echo."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Disable SRM mode (ESC [ 12 h) - turns OFF echo
    parser.feed("\x1b[12h")

    # Should disable local echo
    assert not board.modes.local_echo


def test_srm_enable_local_echo():
    """Test enabling SRM to turn on local echo."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Disable echo first
    parser.feed("\x1b[12h")
    assert not board.modes.local_echo

    # Enable SRM mode (ESC [ 12 l) - turns ON echo
    parser.feed("\x1b[12l")

    # Should enable local echo
    assert board.modes.local_echo


def test_srm_affects_input_echo():
    """Test that SRM mode affects whether input is echoed to screen."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # With echo enabled (default), typing should echo to screen
    board.blitter.write_text("test")
    assert board.blitter.current_buffer.get_line_text(0).startswith("test")

    # Clear screen
    board.blitter.clear_screen()

    # Disable echo
    parser.feed("\x1b[12h")

    # Now typing should not echo to screen (in real implementation)
    # For now, we just verify the mode is set correctly
    assert not board.modes.local_echo

    # Re-enable echo
    parser.feed("\x1b[12l")
    assert board.modes.local_echo


def test_srm_password_input_scenario():
    """Test typical password input scenario with SRM."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Simulate sudo asking for password
    board.blitter.write_text("Password: ")

    # Application disables echo for password input
    parser.feed("\x1b[12h")
    assert not board.modes.local_echo

    # User types password (would not echo in real implementation)
    # We just verify echo is disabled

    # Application re-enables echo after password
    parser.feed("\x1b[12l")
    assert board.modes.local_echo


def test_srm_toggle_state():
    """Test toggling SRM state multiple times."""
    board = Board(width=20, height=5)
    parser = Parser(board)

    # Start with default (echo enabled)
    assert board.modes.local_echo

    # Disable echo
    parser.feed("\x1b[12h")
    assert not board.modes.local_echo

    # Enable echo
    parser.feed("\x1b[12l")
    assert board.modes.local_echo

    # Disable again
    parser.feed("\x1b[12h")
    assert not board.modes.local_echo
