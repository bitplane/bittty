import pytest
from bittty.parser import Parser
from bittty.constants import (
    DECAWM_AUTOWRAP,
    DECCOLM_COLUMN_MODE,
    DECSCNM_SCREEN_MODE,
    DECOM_ORIGIN_MODE,
    DECARSM_AUTO_RESIZE,
    DECKBUM_KEYBOARD_USAGE,
    ESC,
)


# Use real terminal instead of mock
@pytest.fixture
def terminal(standard_terminal):
    """Return a real Terminal instance for testing."""
    return standard_terminal


def test_csi_sm_rm_private_autowrap(terminal):
    """Test CSI ? 7 h (Set Auto-wrap Mode) and CSI ? 7 l (Reset Auto-wrap Mode)."""
    parser = Parser(terminal)

    # Set auto-wrap mode
    parser.feed(f"{ESC}[?{DECAWM_AUTOWRAP}h")
    assert terminal.auto_wrap is True

    # Reset auto-wrap mode
    parser.feed(f"{ESC}[?{DECAWM_AUTOWRAP}l")
    assert terminal.auto_wrap is False


def test_csi_sm_rm_private_cursor_visibility(terminal):
    """Test CSI ? 25 h (Show Cursor) and CSI ? 25 l (Hide Cursor)."""
    parser = Parser(terminal)

    # Hide cursor
    parser.feed("\x1b[?25l")
    assert terminal.cursor_visible is False

    # Show cursor
    parser.feed("\x1b[?25h")
    assert terminal.cursor_visible is True


def test_parse_byte_csi_intermediate_transition(terminal):
    """Test _parse_byte transitions with intermediate characters."""
    parser = Parser(terminal)
    parser.feed("\x1b[?1h")  # ESC [ ? 1 h (CSI with intermediate '?')
    assert parser.current_state == "GROUND"
    assert parser.parsed_params == [1]
    assert parser.intermediate_chars == ["?"]

    parser.reset()
    parser.feed("\x1b[>1c")  # ESC [ > 1 c (CSI with intermediate '>')
    assert parser.current_state == "GROUND"
    assert parser.parsed_params == [1]
    assert parser.intermediate_chars == [">"]


def test_parse_byte_ht_wraps_cursor(terminal):
    """Test that HT character (0x09) wraps cursor_x if it exceeds terminal width."""
    parser = Parser(terminal)
    terminal.cursor_x = terminal.width - 5  # 5 characters before end
    parser.feed("\x09")
    assert terminal.cursor_x == terminal.width - 1  # Should cap at terminal width - 1


def test_parse_byte_unknown_escape_sequence(terminal):
    """Test that an unknown escape sequence returns to GROUND state."""
    parser = Parser(terminal)
    parser.feed("\x1bX")  # ESC then an unknown char 'X'
    assert parser.current_state == "GROUND"


def test_parse_byte_invalid_csi_entry(terminal):
    """Test that an invalid byte in CSI_ENTRY returns to GROUND state."""
    parser = Parser(terminal)
    parser.feed("\x1b[\x01")  # ESC [ then an invalid byte (STX)
    assert parser.current_state == "GROUND"


def test_parse_byte_invalid_csi_param(terminal):
    """Test that an invalid byte in CSI_PARAM returns to GROUND state."""
    parser = Parser(terminal)
    parser.feed("\x1b[1;\x01")  # ESC [ 1 ; then an invalid byte (STX)
    assert parser.current_state == "GROUND"


def test_parse_byte_invalid_csi_intermediate(terminal):
    """Test that an invalid byte in CSI_INTERMEDIATE returns to GROUND state."""
    parser = Parser(terminal)
    parser.feed("\x1b[?1\x01")  # ESC [ ? 1 then an invalid byte (STX)
    assert parser.current_state == "GROUND"


def test_parse_byte_csi_entry_intermediate_general(terminal):
    """Test CSI_ENTRY with general intermediate characters."""
    parser = Parser(terminal)
    parser.feed("\x1b[!p")  # ESC [ ! p (CSI with intermediate '!')
    assert parser.current_state == "GROUND"
    assert parser.intermediate_chars == ["!"]
    assert parser.parsed_params == []


def test_parse_byte_csi_param_intermediate(terminal):
    """Test CSI_PARAM with intermediate characters."""
    parser = Parser(terminal)
    parser.feed("\x1b[1;!p")  # ESC [ 1 ; ! p
    assert parser.current_state == "GROUND"
    # After "1;" we have an empty parameter, which creates [1, None]
    # This is correct behavior - semicolon creates a parameter boundary
    assert parser.parsed_params == [1, None]
    assert parser.intermediate_chars == ["!"]  # ; is a parameter separator, ! is intermediate


def test_parse_byte_csi_intermediate_param_final(terminal):
    """Test CSI_INTERMEDIATE with parameter and final byte."""
    parser = Parser(terminal)

    # Put some text at cursor position first
    terminal.write_text("ABC")
    terminal.cursor_x = 1  # Move cursor to position 1 (between A and B)

    # Send ICH (Insert Character) command: ESC [ ? 1 ; 2 @
    # Should insert 1 blank character at cursor position
    parser.feed("\x1b[?1;2@")

    # Verify that a space was inserted at position 1
    line_text = terminal.current_buffer.get_line_text(0).rstrip()
    assert line_text == "A BC"  # Space inserted between A and BC


def test_split_params_value_error_sub_param(terminal):
    """Test _split_params with ValueError in sub-parameter parsing."""
    parser = Parser(terminal)
    parser._split_params("38:X")  # Malformed sub-parameter
    # Should preserve valid main parameter (38) and ignore invalid sub-parameter
    # This is more useful than discarding the entire parameter
    assert parser.parsed_params == [38]


def test_split_params_value_error_main_param(terminal):
    """Test _split_params with ValueError in main parameter parsing."""
    parser = Parser(terminal)
    parser._split_params("X")  # Malformed main parameter
    assert parser.parsed_params == [0]


def test_csi_dispatch_sm_rm_basic_modes(terminal):
    """Test _csi_dispatch_sm_rm for basic public modes."""
    parser = Parser(terminal)

    # Test auto-wrap mode (public mode 7)
    parser.feed("\x1b[7h")  # Set auto-wrap
    assert terminal.auto_wrap is True
    parser.feed("\x1b[7l")  # Reset auto-wrap
    assert terminal.auto_wrap is False

    # Test cursor visibility (public mode 25)
    parser.feed("\x1b[25l")  # Hide cursor
    assert terminal.cursor_visible is False
    parser.feed("\x1b[25h")  # Show cursor
    assert terminal.cursor_visible is True


def test_csi_sm_rm_deccolm_column_mode(terminal):
    """Test CSI ? 3 h (132 Column Mode) and CSI ? 3 l (80 Column Mode)."""
    parser = Parser(terminal)

    # Set 132 column mode
    parser.feed(f"{ESC}[?{DECCOLM_COLUMN_MODE}h")
    assert terminal.width == 132
    assert terminal.cursor_x == 0  # Cursor should move to home position
    assert terminal.cursor_y == 0

    # Reset to 80 column mode
    parser.feed(f"{ESC}[?{DECCOLM_COLUMN_MODE}l")
    assert terminal.width == 80
    assert terminal.cursor_x == 0  # Cursor should move to home position
    assert terminal.cursor_y == 0


def test_csi_sm_rm_decscnm_screen_mode(terminal):
    """Test CSI ? 5 h (Reverse Screen Mode) and CSI ? 5 l (Normal Screen Mode)."""
    parser = Parser(terminal)

    # Set reverse screen mode
    parser.feed(f"{ESC}[?{DECSCNM_SCREEN_MODE}h")
    assert terminal.reverse_screen is True

    # Reset to normal screen mode
    parser.feed(f"{ESC}[?{DECSCNM_SCREEN_MODE}l")
    assert terminal.reverse_screen is False


def test_csi_sm_rm_decom_origin_mode(terminal):
    """Test CSI ? 6 h (Origin Mode) and CSI ? 6 l (Normal Mode)."""
    parser = Parser(terminal)

    # Set origin mode (relative to scroll region)
    parser.feed(f"{ESC}[?{DECOM_ORIGIN_MODE}h")
    assert terminal.origin_mode is True
    assert terminal.cursor_x == 0  # Cursor should move to origin
    assert terminal.cursor_y == terminal.scroll_top

    # Reset to normal mode (absolute positioning)
    parser.feed(f"{ESC}[?{DECOM_ORIGIN_MODE}l")
    assert terminal.origin_mode is False
    assert terminal.cursor_x == 0  # Cursor should move to home position
    assert terminal.cursor_y == 0


def test_csi_sm_rm_decarsm_auto_resize_mode(terminal):
    """Test CSI ? 2028 h (Auto-Resize Mode) and CSI ? 2028 l (Disable Auto-Resize Mode)."""
    parser = Parser(terminal)

    # Enable auto-resize mode
    parser.feed(f"{ESC}[?{DECARSM_AUTO_RESIZE}h")
    assert terminal.auto_resize_mode is True

    # Disable auto-resize mode
    parser.feed(f"{ESC}[?{DECARSM_AUTO_RESIZE}l")
    assert terminal.auto_resize_mode is False


def test_csi_sm_rm_deckbum_keyboard_usage_mode(terminal):
    """Test CSI ? 69 h (Keyboard Usage Mode) and CSI ? 69 l (Normal Keyboard Mode)."""
    parser = Parser(terminal)

    # Enable keyboard usage mode (typewriter keys send functions)
    parser.feed(f"{ESC}[?{DECKBUM_KEYBOARD_USAGE}h")
    assert terminal.keyboard_usage_mode is True

    # Reset to normal keyboard mode
    parser.feed(f"{ESC}[?{DECKBUM_KEYBOARD_USAGE}l")
    assert terminal.keyboard_usage_mode is False
