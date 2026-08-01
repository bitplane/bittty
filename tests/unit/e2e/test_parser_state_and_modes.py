import pytest

from bittty.constants import (
    DECAWM_AUTOWRAP,
    DECCOLM_COLUMN_MODE,
    DECOM_ORIGIN_MODE,
    ESC,
)
from bittty.parser import Parser


# Use real terminal instead of mock
@pytest.fixture
def board(standard_board):
    """Return a real Board instance for testing."""
    return standard_board


def test_csi_sm_rm_private_autowrap(board):
    """Test CSI ? 7 h (Set Auto-wrap Mode) and CSI ? 7 l (Reset Auto-wrap Mode)."""
    parser = Parser(board)

    # Set auto-wrap mode
    parser.feed(f"{ESC}[?{DECAWM_AUTOWRAP}h")
    assert board.modes.auto_wrap is True

    # Reset auto-wrap mode
    parser.feed(f"{ESC}[?{DECAWM_AUTOWRAP}l")
    assert board.modes.auto_wrap is False


def test_csi_sm_rm_private_cursor_visibility(board):
    """Test CSI ? 25 h (Show Cursor) and CSI ? 25 l (Hide Cursor)."""
    parser = Parser(board)

    # Hide cursor
    parser.feed("\x1b[?25l")
    assert board.modes.cursor_visible is False

    # Show cursor
    parser.feed("\x1b[?25h")
    assert board.modes.cursor_visible is True


def test_parse_byte_csi_intermediate_transition(board):
    """Test CSI parsing with intermediate characters."""
    from bittty.parser.csi import parse_csi_params

    # Test CSI with intermediate '?'
    params, intermediates, final = parse_csi_params("\x1b[?1h")
    assert params == [1]
    assert intermediates == ["?"]
    assert final == "h"

    # Test CSI with intermediate '>'
    params, intermediates, final = parse_csi_params("\x1b[>1c")
    assert params == [1]
    assert intermediates == [">"]
    assert final == "c"


def test_parse_byte_ht_wraps_cursor(board):
    """Test that HT character (0x09) wraps cursor_x if it exceeds terminal width."""
    parser = Parser(board)
    board.cursor.x = board.width - 5  # 5 characters before end
    parser.feed("\x09")
    assert board.cursor.x == board.width - 1  # Should cap at terminal width - 1


def test_unknown_escape_sequences_ignored(board):
    """Test that unknown escape sequences are ignored and don't affect normal parsing."""
    parser = Parser(board)

    # Unknown escape sequences should be logged but not crash
    parser.feed("Before\x1b9After")  # ESC 9 (unknown/unhandled)
    parser.feed("\x1b:")  # ESC : (unknown)
    parser.feed("End")

    # Text should still be processed normally
    text_content = board.blitter.current_buffer.get_line_text(0).strip()
    assert "Before" in text_content
    assert "After" in text_content
    assert "End" in text_content


def test_invalid_csi_sequences_ignored(board):
    """Test that invalid CSI sequences are ignored and don't affect normal parsing."""
    parser = Parser(board)

    # Invalid CSI sequences behavior matches real terminals
    parser.feed("Hello\x1b[\x01World")  # Invalid control in CSI

    # Based on tmux behavior: "Hello" appears, CSI is abandoned, "orld" appears (W consumed)
    text_content = board.blitter.current_buffer.get_line_text(0).strip()
    assert "Hello" in text_content
    assert "orld" in text_content

    # Test recovery with more text
    parser.feed("More")
    text_content = board.blitter.current_buffer.get_line_text(0).strip()
    assert "More" in text_content


def test_malformed_csi_recovery(board):
    """Test that parser recovers from malformed CSI sequences."""
    parser = Parser(board)

    # Feed an unhandled CSI (final byte W) followed by normal text
    parser.feed("Start\x1b[999;999;999WEnd")  # Unknown CSI sequence

    # Should still write the text parts
    text_content = board.blitter.current_buffer.get_line_text(0).strip()
    assert "Start" in text_content
    assert "End" in text_content


def test_incomplete_csi_sequences(board):
    """Test handling of incomplete CSI sequences."""
    parser = Parser(board)

    # Incomplete sequences shouldn't crash
    parser.feed("Test\x1b[")  # Just CSI introducer
    parser.feed("5;2")  # More CSI params (not a final byte)
    parser.feed("H")  # CSI final byte - completes as cursor position

    # Should have processed "Test" and positioned cursor
    text_content = board.blitter.current_buffer.get_line_text(0).strip()
    assert "Test" in text_content

    # Test actual incomplete sequences that stay incomplete
    parser.feed("Next\x1b[1;")  # CSI with trailing semicolon
    parser.feed("3")  # Add more param
    parser.feed("3m")  # Complete with SGR

    # "Next" should appear (cursor was moved by H earlier)
    assert "Next" in board.blitter.current_buffer.get_line_text(4).strip()


def test_parse_byte_csi_entry_intermediate_general(board):
    """Test CSI parsing with general intermediate characters."""
    from bittty.parser.csi import parse_csi_params

    # Test CSI with intermediate '!'
    params, intermediates, final = parse_csi_params("\x1b[!p")
    assert intermediates == ["!"]
    assert params == []
    assert final == "p"


def test_parse_byte_csi_param_intermediate(board):
    """Test CSI parsing with parameters and intermediate characters."""
    from bittty.parser.csi import parse_csi_params

    # Test CSI with parameter and intermediate
    params, intermediates, final = parse_csi_params("\x1b[1;!p")
    # After "1;" we have an empty parameter, which creates [1, None]
    # This is correct behavior - semicolon creates a parameter boundary
    assert params == [1, None]
    assert intermediates == ["!"]  # ; is a parameter separator, ! is intermediate
    assert final == "p"


def test_parse_byte_csi_intermediate_param_final(board):
    """Test CSI_INTERMEDIATE with parameter and final byte."""
    parser = Parser(board)

    # Put some text at cursor position first
    board.blitter.write_text("ABC")
    board.cursor.x = 1  # Move cursor to position 1 (between A and B)

    # Send ICH (Insert Character) command: ESC [ ? 1 ; 2 @
    # Should insert 1 blank character at cursor position
    parser.feed("\x1b[?1;2@")

    # Verify that a space was inserted at position 1
    line_text = board.blitter.current_buffer.get_line_text(0).rstrip()
    assert line_text == "A BC"  # Space inserted between A and BC


def test_csi_params_with_sub_parameters(board):
    """Test CSI parsing with sub-parameters (colon notation)."""
    from bittty.parser.csi import parse_csi_params

    # Test sub-parameter parsing - should preserve main parameter (38) and ignore malformed sub-param
    params, intermediates, final = parse_csi_params("\x1b[38:Xm")
    assert params == [38]  # Main parameter preserved, invalid sub-parameter ignored
    assert intermediates == []
    assert final == "m"


def test_csi_params_with_invalid_main_param(board):
    """A non-numeric parameter reads as absent, never as a string.

    ECMA-48 parameter values are digits. Preserving the raw text put a str in a
    tuple every handler downstream does arithmetic on, so `CSI : M` reached
    delete_lines() and raised TypeError on hostile input.
    """
    from bittty.parser.csi import parse_csi_params

    params, intermediates, final = parse_csi_params("\x1b[Xm")
    assert params == [None]  # absent -> the operation's default
    assert final == "m"

    # The form that actually crashed: a leading sub-parameter separator.
    params, _, final = parse_csi_params("\x1b[:M")
    assert params == [None]
    assert final == "M"


def test_csi_dispatch_sm_rm_basic_modes(board):
    """Autowrap and cursor visibility are DEC private modes (?7 / ?25)."""
    parser = Parser(board)

    # Test auto-wrap mode (private mode ?7)
    parser.feed("\x1b[?7h")  # Set auto-wrap
    assert board.modes.auto_wrap is True
    parser.feed("\x1b[?7l")  # Reset auto-wrap
    assert board.modes.auto_wrap is False

    # Test cursor visibility (private mode ?25)
    parser.feed("\x1b[?25l")  # Hide cursor
    assert board.modes.cursor_visible is False
    parser.feed("\x1b[?25h")  # Show cursor
    assert board.modes.cursor_visible is True


def test_csi_sm_rm_deccolm_column_mode(board):
    """Test CSI ? 3 h (132 Column Mode) and CSI ? 3 l (80 Column Mode)."""
    parser = Parser(board)

    # Without mode 40 (allowC132), DECCOLM is ignored — reset strings carry ?3l
    # and must not shrink the terminal.
    parser.feed(f"{ESC}[?{DECCOLM_COLUMN_MODE}h")
    assert board.width == 80

    parser.feed(f"{ESC}[?40h")  # permit 80<->132 switching
    parser.feed(f"{ESC}[?{DECCOLM_COLUMN_MODE}h")
    assert board.width == 132
    assert board.cursor.x == 0  # Cursor should move to home position
    assert board.cursor.y == 0

    # Reset to 80 column mode
    parser.feed(f"{ESC}[?{DECCOLM_COLUMN_MODE}l")
    assert board.width == 80
    assert board.cursor.x == 0  # Cursor should move to home position
    assert board.cursor.y == 0


def test_csi_sm_rm_decom_origin_mode(board):
    """Test CSI ? 6 h (Origin Mode) and CSI ? 6 l (Normal Mode)."""
    parser = Parser(board)

    # Set origin mode (relative to scroll region)
    parser.feed(f"{ESC}[?{DECOM_ORIGIN_MODE}h")
    assert board.modes.origin_mode is True
    assert board.cursor.x == 0  # Cursor should move to origin
    assert board.cursor.y == board.blitter.scroll_top

    # Reset to normal mode (absolute positioning)
    parser.feed(f"{ESC}[?{DECOM_ORIGIN_MODE}l")
    assert board.modes.origin_mode is False
    assert board.cursor.x == 0  # Cursor should move to home position
    assert board.cursor.y == 0


def test_deccolm_clears_the_screen_and_resets_the_region(board):
    """DECCOLM always erases the display and restores the full scroll region."""
    parser = Parser(board)
    parser.feed(f"{ESC}[?40h")  # permit column switching
    parser.feed("some text")
    parser.feed(f"{ESC}[5;15r")  # shrink the scroll region

    parser.feed(f"{ESC}[?{DECCOLM_COLUMN_MODE}h")

    assert board.width == 132
    assert board.blitter.current_buffer.get_line_text(0).strip() == ""
    assert board.blitter.scroll_top == 0
    assert board.blitter.scroll_bottom == board.height - 1
