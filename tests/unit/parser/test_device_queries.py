"""Test device query responses and capabilities."""

from unittest.mock import Mock
from bittty.terminal import Terminal
from bittty.parser import Parser


def test_cursor_position_report():
    """Test CSI 6 n (Cursor Position Report)."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method to capture responses
    terminal.respond = Mock()

    # Move cursor to position (5, 10) - 0-based
    terminal.cursor_x = 10
    terminal.cursor_y = 5

    # Send cursor position report query
    parser.feed("\x1b[6n")  # ESC [ 6 n

    # Should respond with cursor position (1-based)
    terminal.respond.assert_called_once_with("\033[6;11R")


def test_device_status_report():
    """Test CSI 5 n (Device Status Report)."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Send device status report query
    parser.feed("\x1b[5n")  # ESC [ 5 n

    # Should respond with OK status
    terminal.respond.assert_called_once_with("\033[0n")


def test_device_attributes_primary():
    """Test CSI c (Primary Device Attributes)."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Send primary device attributes query
    parser.feed("\x1b[c")  # ESC [ c

    # Should respond with VT220 capabilities
    terminal.respond.assert_called_once_with("\033[?62;1;2;6;8;9;15;18;21;22c")


def test_device_attributes_with_param():
    """Test CSI 0 c (Primary Device Attributes with explicit parameter)."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Send primary device attributes query with explicit 0 parameter
    parser.feed("\x1b[0c")  # ESC [ 0 c

    # Should respond with VT220 capabilities
    terminal.respond.assert_called_once_with("\033[?62;1;2;6;8;9;15;18;21;22c")


def test_decrqm_private_mode_query_cursor_keys():
    """Test DECRQM private mode query for cursor keys application mode."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Test with cursor keys in normal mode
    terminal.cursor_application_mode = False
    parser.feed("\x1b[?1$p")  # ESC [ ? 1 $ p

    # Should respond with mode reset (2)
    terminal.respond.assert_called_with("\033[?1;2$y")

    # Reset mock and test with cursor keys in application mode
    terminal.respond.reset_mock()
    terminal.cursor_application_mode = True
    parser.feed("\x1b[?1$p")  # ESC [ ? 1 $ p

    # Should respond with mode set (1)
    terminal.respond.assert_called_with("\033[?1;1$y")


def test_decrqm_private_mode_query_autowrap():
    """Test DECRQM private mode query for autowrap mode."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Test with autowrap enabled (default)
    terminal.auto_wrap = True
    parser.feed("\x1b[?7$p")  # ESC [ ? 7 $ p

    # Should respond with mode set (1)
    terminal.respond.assert_called_with("\033[?7;1$y")

    # Reset mock and test with autowrap disabled
    terminal.respond.reset_mock()
    terminal.auto_wrap = False
    parser.feed("\x1b[?7$p")  # ESC [ ? 7 $ p

    # Should respond with mode reset (2)
    terminal.respond.assert_called_with("\033[?7;2$y")


def test_decrqm_private_mode_query_cursor_visibility():
    """Test DECRQM private mode query for cursor visibility."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Test with cursor visible (default)
    terminal.cursor_visible = True
    parser.feed("\x1b[?25$p")  # ESC [ ? 25 $ p

    # Should respond with mode set (1)
    terminal.respond.assert_called_with("\033[?25;1$y")

    # Reset mock and test with cursor hidden
    terminal.respond.reset_mock()
    terminal.cursor_visible = False
    parser.feed("\x1b[?25$p")  # ESC [ ? 25 $ p

    # Should respond with mode reset (2)
    terminal.respond.assert_called_with("\033[?25;2$y")


def test_decrqm_private_mode_query_alternate_screen():
    """Test DECRQM private mode query for alternate screen buffer."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Test with primary screen (default)
    terminal.in_alt_screen = False
    parser.feed("\x1b[?1049$p")  # ESC [ ? 1049 $ p

    # Should respond with mode reset (2)
    terminal.respond.assert_called_with("\033[?1049;2$y")

    # Reset mock and test with alternate screen
    terminal.respond.reset_mock()
    terminal.in_alt_screen = True
    parser.feed("\x1b[?1049$p")  # ESC [ ? 1049 $ p

    # Should respond with mode set (1)
    terminal.respond.assert_called_with("\033[?1049;1$y")


def test_decrqm_ansi_mode_query_insert_mode():
    """Test DECRQM ANSI mode query for insert/replace mode."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Test with replace mode (default)
    terminal.insert_mode = False
    parser.feed("\x1b[4$p")  # ESC [ 4 $ p

    # Should respond with mode reset (2) - no ? prefix for ANSI modes
    terminal.respond.assert_called_with("\033[4;2$y")

    # Reset mock and test with insert mode
    terminal.respond.reset_mock()
    terminal.insert_mode = True
    parser.feed("\x1b[4$p")  # ESC [ 4 $ p

    # Should respond with mode set (1)
    terminal.respond.assert_called_with("\033[4;1$y")


def test_decrqm_unrecognized_mode():
    """Test DECRQM response for unrecognized modes."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Test unrecognized private mode
    parser.feed("\x1b[?9999$p")  # ESC [ ? 9999 $ p

    # Should respond with not recognized (0)
    terminal.respond.assert_called_with("\033[?9999;0$y")

    # Reset mock and test unrecognized ANSI mode
    terminal.respond.reset_mock()
    parser.feed("\x1b[9999$p")  # ESC [ 9999 $ p

    # Should respond with not recognized (0)
    terminal.respond.assert_called_with("\033[9999;0$y")


def test_multiple_device_queries():
    """Test multiple device queries in sequence."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # Move cursor to a specific position
    terminal.cursor_x = 15
    terminal.cursor_y = 10

    # Send multiple queries
    parser.feed("\x1b[6n")  # Cursor Position Report
    parser.feed("\x1b[5n")  # Device Status Report
    parser.feed("\x1b[c")  # Device Attributes

    # Should have called respond three times
    assert terminal.respond.call_count == 3

    # Check the responses
    expected_calls = [
        (("\033[11;16R",), {}),  # CPR: row 11, col 16 (1-based)
        (("\033[0n",), {}),  # DSR: OK status
        (("\033[?62;1;2;6;8;9;15;18;21;22c",), {}),  # DA: VT220 capabilities
    ]

    assert terminal.respond.call_args_list == expected_calls


def test_vim_compatibility_queries():
    """Test the specific queries that vim uses for underline detection."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock the respond method
    terminal.respond = Mock()

    # These are the queries vim sends that were causing issues
    parser.feed("\x1b[c")  # Device Attributes
    parser.feed("\x1b[>c")  # Secondary Device Attributes (also responds as primary)
    parser.feed("\x1b[?1$p")  # Query cursor keys mode
    parser.feed("\x1b[?25$p")  # Query cursor visibility mode

    # Should respond to all implemented queries (including >c which we treat as c)
    assert terminal.respond.call_count == 4  # DA, secondary DA, DECRQM for mode 1, DECRQM for mode 25

    # Check specific responses
    calls = [call[0][0] for call in terminal.respond.call_args_list]
    assert "\033[?62;1;2;6;8;9;15;18;21;22c" in calls  # Device Attributes (appears twice)
    assert "\033[?1;2$y" in calls  # Cursor keys mode (reset by default)
    assert "\033[?25;1$y" in calls  # Cursor visibility (set by default)


def test_terminal_respond_vs_send():
    """Test that device queries use respond() for immediate flush."""
    terminal = Terminal(width=80, height=24)
    parser = Parser(terminal)

    # Mock both send and respond methods
    terminal.send = Mock()
    terminal.respond = Mock()

    # Send device query
    parser.feed("\x1b[6n")  # Cursor Position Report

    # Should use respond(), not send()
    terminal.respond.assert_called_once()
    terminal.send.assert_not_called()

    # Reset mocks and test regular input
    terminal.send.reset_mock()
    terminal.respond.reset_mock()

    # Send regular character (this goes through input processing)
    terminal.input("A")

    # Should use send(), not respond()
    terminal.send.assert_called_once()
    terminal.respond.assert_not_called()
