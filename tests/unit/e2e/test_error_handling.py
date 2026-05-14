"""Tests for parser error handling and edge cases."""

from bittty.parser import Parser
from bittty.terminal import Terminal


def test_csi_invalid_characters():
    """Test CSI sequence with invalid characters."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # CSI with invalid character should abort sequence
    parser.feed("\x1b[\x01A")  # Invalid control character in CSI
    parser.feed("Hello")

    # Should continue normally after invalid sequence
    content = terminal.current_buffer.get_line_text(0)
    assert "Hello" in content


def test_csi_private_parameter_in_wrong_state():
    """Test private parameter bytes in wrong CSI state."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Private parameter byte after regular parameter
    parser.feed("\x1b[1;?25h")  # ? after number should be invalid
    parser.feed("Test")

    # Should handle gracefully
    content = terminal.current_buffer.get_line_text(0)
    assert "Test" in content


def test_window_operations_ignored():
    """Test that window operations CSI sequences are ignored."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Window operation sequences (CSI Ps t)
    parser.feed("\x1b[8;24;80t")  # Resize window
    parser.feed("\x1b[11t")  # Report window state
    parser.feed("Normal text")

    # Should work normally after window operations
    content = terminal.current_buffer.get_line_text(0)
    assert "Normal text" in content


def test_device_status_queries_ignored():
    """Test that device status queries are ignored."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Device status queries
    parser.feed("\x1b[6n")  # Cursor position report
    parser.feed("\x1b[5n")  # Device status report
    parser.feed("\x1b[?25h")  # Show cursor
    parser.feed("Text")

    content = terminal.current_buffer.get_line_text(0)
    assert "Text" in content


def test_privacy_message_ignored():
    """Test that privacy messages are ignored."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Privacy message (CSI Ps ^)
    parser.feed("\x1b[1^")
    parser.feed("After PM")

    content = terminal.current_buffer.get_line_text(0)
    assert "After PM" in content


def test_device_attributes_ignored():
    """Test that device attributes queries are ignored."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Device attributes (CSI Ps c)
    parser.feed("\x1b[0c")
    parser.feed("\x1b[1;2c")
    parser.feed("Content")

    content = terminal.current_buffer.get_line_text(0)
    assert "Content" in content


def test_sgr_with_no_parameters():
    """Test SGR sequence with no parameters defaults to reset."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Set some style first
    parser.feed("\x1b[31m")  # Red
    parser.feed("Red")

    # SGR with no parameters should reset
    parser.feed("\x1b[m")
    parser.feed("Default")

    # Check that style was reset for "Default" text
    content = terminal.current_buffer.get_content()
    red_style = content[0][0][0]  # First char style
    default_style = content[0][3][0]  # "Default" first char style

    # They should be different (red vs default)
    assert red_style != default_style


def test_unknown_csi_sequence_logged():
    """Test that unknown CSI sequences are handled gracefully."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Unknown CSI sequence
    parser.feed("\x1b[999z")  # Unknown final character
    parser.feed("After unknown")

    content = terminal.current_buffer.get_line_text(0)
    assert "After unknown" in content
