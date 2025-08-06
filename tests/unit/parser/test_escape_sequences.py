import pytest
from unittest.mock import Mock
from bittty.parser import Parser
from bittty.terminal import Terminal
from bittty.constants import ESC, BEL, ERASE_ALL


@pytest.fixture
def terminal():
    """Return a mock Screen object."""
    terminal = Mock(spec=Terminal)
    terminal.current_style = Mock()  # Mock the Style object
    terminal.width = 80  # Set a default width for tab tests
    terminal.height = 24  # Set a default height for scroll tests
    terminal.scroll_top = 0  # Set default scroll region top
    terminal.scroll_bottom = terminal.height - 1  # Set default scroll region bottom
    return terminal


def test_bell_character(terminal):
    """Test that the BEL character (0x07) calls terminal.bell() method."""
    parser = Parser(terminal)
    parser.feed(BEL)
    # BEL should call the bell method but not cause visible terminal changes
    terminal.bell.assert_called_once()
    terminal.write_text.assert_not_called()
    terminal.backspace.assert_not_called()
    terminal.line_feed.assert_not_called()
    terminal.carriage_return.assert_not_called()


def test_escape_to_csi_entry(terminal):
    """Test transition from ESCAPE to CSI_ENTRY state."""
    parser = Parser(terminal)
    parser.feed(f"{ESC}[")  # ESC then [


def test_ris_reset_terminal(terminal):
    """Test RIS (Reset to Initial State) sequence."""
    parser = Parser(terminal)
    parser.feed(f"{ESC}c")  # ESC then c
    terminal.clear_screen.assert_called_once_with(ERASE_ALL)
    terminal.set_cursor.assert_called_once_with(0, 0)


def test_ind_index(terminal):
    """Test IND (Index) sequence."""
    parser = Parser(terminal)
    parser.feed("\x1bD")  # ESC then D
    terminal.line_feed.assert_called_once()


def test_ri_reverse_index_no_scroll(terminal):
    """Test RI (Reverse Index) sequence without scrolling."""
    parser = Parser(terminal)
    terminal.cursor_y = 5
    terminal.scroll_top = 0
    parser.feed("\x1bM")  # ESC then M
    assert terminal.cursor_y == 4
    terminal.scroll_down.assert_not_called()


def test_ri_reverse_index_with_scroll(terminal):
    """Test RI (Reverse Index) sequence with scrolling."""
    parser = Parser(terminal)
    terminal.cursor_y = 0  # At the top of the scroll region
    terminal.scroll_top = 0
    parser.feed("\x1bM")  # ESC then M
    terminal.scroll.assert_called_once_with(-1)


def test_desc_save_cursor(terminal):
    """Test DECSC (Save Cursor) sequence."""
    parser = Parser(terminal)
    parser.feed("\x1b7")  # ESC then 7
    terminal.save_cursor.assert_called_once()


def test_decrc_restore_cursor(terminal):
    """Test DECRC (Restore Cursor) sequence."""
    parser = Parser(terminal)
    parser.feed("\x1b8")  # ESC then 8
    terminal.restore_cursor.assert_called_once()
