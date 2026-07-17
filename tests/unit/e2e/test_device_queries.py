"""Test device query responses and capabilities."""

from bittty import Board
from bittty.parser import Parser


class RecordingTransport:
    def __init__(self):
        self.data = []
        self.flush_count = 0

    def write(self, data):
        self.data.append(data)

    def flush(self):
        self.flush_count += 1


def terminal_with_transport(width=80, height=24):
    terminal = Board(width=width, height=height)
    transport = RecordingTransport()
    terminal.host.attach(transport)
    return terminal, Parser(terminal), transport


def test_cursor_position_report():
    """Test CSI 6 n (Cursor Position Report)."""
    terminal, parser, transport = terminal_with_transport()

    # Move cursor to position (5, 10) - 0-based
    terminal.cursor.x = 10
    terminal.cursor.y = 5

    # Send cursor position report query
    parser.feed("\x1b[6n")  # ESC [ 6 n

    # Should respond with cursor position (1-based)
    assert transport.data == ["\033[6;11R"]
    assert transport.flush_count == 1


def test_device_status_report():
    """Test CSI 5 n (Device Status Report)."""
    _terminal, parser, transport = terminal_with_transport()

    # Send device status report query
    parser.feed("\x1b[5n")  # ESC [ 5 n

    # Should respond with OK status
    assert transport.data == ["\033[0n"]
    assert transport.flush_count == 1


def test_device_attributes_primary():
    """Test CSI c (Primary Device Attributes)."""
    _terminal, parser, transport = terminal_with_transport()

    # Send primary device attributes query
    parser.feed("\x1b[c")  # ESC [ c

    # Should respond with VT220 capabilities
    assert transport.data == ["\033[?62;1;6;8;9;15;18;21;22;23c"]
    assert transport.flush_count == 1


def test_device_attributes_with_param():
    """Test CSI 0 c (Primary Device Attributes with explicit parameter)."""
    _terminal, parser, transport = terminal_with_transport()

    # Send primary device attributes query with explicit 0 parameter
    parser.feed("\x1b[0c")  # ESC [ 0 c

    # Should respond with VT220 capabilities
    assert transport.data == ["\033[?62;1;6;8;9;15;18;21;22;23c"]
    assert transport.flush_count == 1


def test_decrqm_private_mode_query_cursor_keys():
    """Test DECRQM private mode query for cursor keys application mode."""
    terminal, parser, transport = terminal_with_transport()

    # Test with cursor keys in normal mode
    terminal.modes.cursor_application_mode = False
    parser.feed("\x1b[?1$p")  # ESC [ ? 1 $ p

    # Should respond with mode reset (2)
    assert transport.data[-1] == "\033[?1;2$y"

    terminal.modes.cursor_application_mode = True
    parser.feed("\x1b[?1$p")  # ESC [ ? 1 $ p

    # Should respond with mode set (1)
    assert transport.data[-1] == "\033[?1;1$y"
    assert transport.flush_count == 2


def test_decrqm_private_mode_query_autowrap():
    """Test DECRQM private mode query for autowrap mode."""
    terminal, parser, transport = terminal_with_transport()

    # Test with autowrap enabled (default)
    terminal.modes.auto_wrap = True
    parser.feed("\x1b[?7$p")  # ESC [ ? 7 $ p

    # Should respond with mode set (1)
    assert transport.data[-1] == "\033[?7;1$y"

    terminal.modes.auto_wrap = False
    parser.feed("\x1b[?7$p")  # ESC [ ? 7 $ p

    # Should respond with mode reset (2)
    assert transport.data[-1] == "\033[?7;2$y"
    assert transport.flush_count == 2


def test_decrqm_private_mode_query_cursor_visibility():
    """Test DECRQM private mode query for cursor visibility."""
    terminal, parser, transport = terminal_with_transport()

    # Test with cursor visible (default)
    terminal.modes.cursor_visible = True
    parser.feed("\x1b[?25$p")  # ESC [ ? 25 $ p

    # Should respond with mode set (1)
    assert transport.data[-1] == "\033[?25;1$y"

    terminal.modes.cursor_visible = False
    parser.feed("\x1b[?25$p")  # ESC [ ? 25 $ p

    # Should respond with mode reset (2)
    assert transport.data[-1] == "\033[?25;2$y"
    assert transport.flush_count == 2


def test_decrqm_private_mode_query_alternate_screen():
    """Test DECRQM private mode query for alternate screen buffer."""
    terminal, parser, transport = terminal_with_transport()

    # Test with primary screen (default)
    terminal.blitter.in_alt_screen = False
    parser.feed("\x1b[?1049$p")  # ESC [ ? 1049 $ p

    # Should respond with mode reset (2)
    assert transport.data[-1] == "\033[?1049;2$y"

    terminal.blitter.in_alt_screen = True
    parser.feed("\x1b[?1049$p")  # ESC [ ? 1049 $ p

    # Should respond with mode set (1)
    assert transport.data[-1] == "\033[?1049;1$y"
    assert transport.flush_count == 2


def test_decrqm_private_mode_query_ansi_mode_default():
    """DECANM status query should not require prior mode initialization by parser."""
    _terminal, parser, transport = terminal_with_transport()

    parser.feed("\x1b[?2$p")

    assert transport.data == ["\033[?2;1$y"]


def test_decrqm_ansi_mode_query_insert_mode():
    """Test DECRQM ANSI mode query for insert/replace mode."""
    terminal, parser, transport = terminal_with_transport()

    # Test with replace mode (default)
    terminal.modes.insert_mode = False
    parser.feed("\x1b[4$p")  # ESC [ 4 $ p

    # Should respond with mode reset (2) - no ? prefix for ANSI modes
    assert transport.data[-1] == "\033[4;2$y"

    terminal.modes.insert_mode = True
    parser.feed("\x1b[4$p")  # ESC [ 4 $ p

    # Should respond with mode set (1)
    assert transport.data[-1] == "\033[4;1$y"
    assert transport.flush_count == 2


def test_decrqm_unrecognized_mode():
    """Test DECRQM response for unrecognized modes."""
    _terminal, parser, transport = terminal_with_transport()

    # Test unrecognized private mode
    parser.feed("\x1b[?9999$p")  # ESC [ ? 9999 $ p

    # Should respond with not recognized (0)
    assert transport.data[-1] == "\033[?9999;0$y"

    parser.feed("\x1b[9999$p")  # ESC [ 9999 $ p

    # Should respond with not recognized (0)
    assert transport.data[-1] == "\033[9999;0$y"
    assert transport.flush_count == 2


def test_multiple_device_queries():
    """Test multiple device queries in sequence."""
    terminal, parser, transport = terminal_with_transport()

    # Move cursor to a specific position
    terminal.cursor.x = 15
    terminal.cursor.y = 10

    # Send multiple queries
    parser.feed("\x1b[6n")  # Cursor Position Report
    parser.feed("\x1b[5n")  # Device Status Report
    parser.feed("\x1b[c")  # Device Attributes

    assert transport.data == [
        "\033[11;16R",
        "\033[0n",
        "\033[?62;1;6;8;9;15;18;21;22;23c",
    ]
    assert transport.flush_count == 3


def test_vim_compatibility_queries():
    """Test the specific queries that vim uses for underline detection."""
    _terminal, parser, transport = terminal_with_transport()

    # These are the queries vim sends that were causing issues
    parser.feed("\x1b[c")  # Device Attributes
    parser.feed("\x1b[>c")  # Secondary Device Attributes (also responds as primary)
    parser.feed("\x1b[?1$p")  # Query cursor keys mode
    parser.feed("\x1b[?25$p")  # Query cursor visibility mode

    # Should respond to all implemented queries (including >c which we treat as c)
    assert len(transport.data) == 4  # DA, secondary DA, DECRQM for mode 1, DECRQM for mode 25

    # Check specific responses
    assert "\033[?62;1;6;8;9;15;18;21;22;23c" in transport.data  # Device Attributes (appears twice)
    assert "\033[?1;2$y" in transport.data  # Cursor keys mode (reset by default)
    assert "\033[?25;1$y" in transport.data  # Cursor visibility (set by default)
    assert transport.flush_count == 4


def test_terminal_respond_vs_send():
    """Test that device queries use respond() for immediate flush."""
    terminal, parser, transport = terminal_with_transport()

    # Send device query
    parser.feed("\x1b[6n")  # Cursor Position Report

    assert transport.data == ["\033[1;1R"]
    assert transport.flush_count == 1

    # Send regular character (this goes through input processing)
    terminal.input("A")

    assert transport.data == ["\033[1;1R", "A"]
    assert transport.flush_count == 1
