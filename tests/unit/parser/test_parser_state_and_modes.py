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
    """Test CSI parsing with intermediate characters."""
    from bittty.parser.core import parse_csi_sequence

    # Test CSI with intermediate '?'
    params, intermediates, final = parse_csi_sequence("\x1b[?1h")
    assert params == [1]
    assert intermediates == ["?"]
    assert final == "h"

    # Test CSI with intermediate '>'
    params, intermediates, final = parse_csi_sequence("\x1b[>1c")
    assert params == [1]
    assert intermediates == [">"]
    assert final == "c"


def test_parse_byte_ht_wraps_cursor(terminal):
    """Test that HT character (0x09) wraps cursor_x if it exceeds terminal width."""
    parser = Parser(terminal)
    terminal.cursor_x = terminal.width - 5  # 5 characters before end
    parser.feed("\x09")
    assert terminal.cursor_x == terminal.width - 1  # Should cap at terminal width - 1


def test_unknown_escape_sequences_ignored(terminal):
    """Test that unknown escape sequences are ignored and don't affect normal parsing."""
    parser = Parser(terminal)

    # Unknown escape sequences should be logged but not crash
    parser.feed("Before\x1b9After")  # ESC 9 (unknown/unhandled)
    parser.feed("\x1b:")  # ESC : (unknown)
    parser.feed("End")

    # Text should still be processed normally
    text_content = terminal.current_buffer.get_line_text(0).strip()
    assert "Before" in text_content
    assert "After" in text_content
    assert "End" in text_content


def test_invalid_csi_sequences_ignored(terminal):
    """Test that invalid CSI sequences are ignored and don't affect normal parsing."""
    parser = Parser(terminal)

    # Invalid CSI sequences behavior matches real terminals
    parser.feed("Hello\x1b[\x01World")  # Invalid control in CSI

    # Based on tmux behavior: "Hello" appears, CSI is abandoned, "orld" appears (W consumed)
    text_content = terminal.current_buffer.get_line_text(0).strip()
    assert "Hello" in text_content
    assert "orld" in text_content

    # Test recovery with more text
    parser.feed("More")
    text_content = terminal.current_buffer.get_line_text(0).strip()
    assert "More" in text_content


def test_malformed_csi_recovery(terminal):
    """Test that parser recovers from malformed CSI sequences."""
    parser = Parser(terminal)

    # Feed malformed CSI followed by normal text
    parser.feed("Start\x1b[999;999;999ZEnd")  # Unknown CSI sequence

    # Should still write the text parts
    text_content = terminal.current_buffer.get_line_text(0).strip()
    assert "Start" in text_content
    assert "End" in text_content


def test_incomplete_csi_sequences(terminal):
    """Test handling of incomplete CSI sequences."""
    parser = Parser(terminal)

    # Incomplete sequences shouldn't crash
    parser.feed("Test\x1b[")  # Just CSI introducer
    parser.feed("5;2")  # More CSI params (not a final byte)
    parser.feed("H")  # CSI final byte - completes as cursor position

    # Should have processed "Test" and positioned cursor
    text_content = terminal.current_buffer.get_line_text(0).strip()
    assert "Test" in text_content

    # Test actual incomplete sequences that stay incomplete
    parser.feed("Next\x1b[1;")  # CSI with trailing semicolon
    parser.feed("3")  # Add more param
    parser.feed("3m")  # Complete with SGR

    # "Next" should appear (cursor was moved by H earlier)
    assert "Next" in terminal.current_buffer.get_line_text(4).strip()


def test_parse_byte_csi_entry_intermediate_general(terminal):
    """Test CSI parsing with general intermediate characters."""
    from bittty.parser.core import parse_csi_sequence

    # Test CSI with intermediate '!'
    params, intermediates, final = parse_csi_sequence("\x1b[!p")
    assert intermediates == ["!"]
    assert params == []
    assert final == "p"


def test_parse_byte_csi_param_intermediate(terminal):
    """Test CSI parsing with parameters and intermediate characters."""
    from bittty.parser.core import parse_csi_sequence

    # Test CSI with parameter and intermediate
    params, intermediates, final = parse_csi_sequence("\x1b[1;!p")
    # After "1;" we have an empty parameter, which creates [1, None]
    # This is correct behavior - semicolon creates a parameter boundary
    assert params == [1, None]
    assert intermediates == ["!"]  # ; is a parameter separator, ! is intermediate
    assert final == "p"


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


def test_csi_params_with_sub_parameters(terminal):
    """Test CSI parsing with sub-parameters (colon notation)."""
    from bittty.parser.core import parse_csi_sequence

    # Test sub-parameter parsing - should preserve main parameter (38) and ignore malformed sub-param
    params, intermediates, final = parse_csi_sequence("\x1b[38:Xm")
    assert params == [38]  # Main parameter preserved, invalid sub-parameter ignored
    assert intermediates == []
    assert final == "m"


def test_csi_params_with_invalid_main_param(terminal):
    """Test CSI parsing with completely invalid parameters."""
    from bittty.parser.core import parse_csi_sequence

    # Test invalid main parameter - should return empty result (invalid sequence)
    params, intermediates, final = parse_csi_sequence("\x1b[Xm")
    # Invalid sequences return empty params as they don't match fast paths
    # This is correct behavior - invalid sequences should be ignored
    assert params == [] or params == ["X"]  # Either ignored or preserved as string
    assert final == "m"


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
