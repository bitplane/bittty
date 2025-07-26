import pytest
from unittest.mock import Mock
from bittty.parser import Parser
from bittty.terminal import Terminal
from rich.style import Style
from bittty.constants import (
    DEFAULT_TERMINAL_WIDTH,
    DEFAULT_TERMINAL_HEIGHT,
    DECAWM_AUTOWRAP,
    ESC,
)


@pytest.fixture
def terminal():
    """Return a mock Screen object with necessary attributes."""
    terminal = Mock(spec=Terminal)
    terminal.current_style = Style()  # Initialize with a real Style object
    terminal.width = DEFAULT_TERMINAL_WIDTH
    terminal.height = DEFAULT_TERMINAL_HEIGHT
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.scroll_top = 0
    terminal.scroll_bottom = terminal.height - 1
    terminal.auto_wrap = True
    terminal.cursor_visible = True
    terminal.current_ansi_code = ""

    def _set_cursor(x, y):
        if x is not None:
            terminal.cursor_x = x
        if y is not None:
            terminal.cursor_y = y

    terminal.set_cursor.side_effect = _set_cursor
    return terminal


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
    parser.feed("\x1b[?1;2@")  # ESC [ ? 1 ; 2 @
    # ICH uses the first parameter (index 0), which is 1
    terminal.insert_characters.assert_called_once_with(1, terminal.current_ansi_code)


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
