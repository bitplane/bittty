from bittty.parser import Parser
from bittty.constants import ESC, BEL


def test_bell_character(terminal):
    """Test that the BEL character (0x07) processes without causing visible changes."""
    parser = Parser(terminal.board)
    initial_cursor = (terminal.board.cursor.x, terminal.board.cursor.y)
    initial_text = terminal.board.blitter.current_buffer.get_line_text(0)

    parser.feed(BEL)

    # BEL should not cause visible terminal changes
    assert (terminal.board.cursor.x, terminal.board.cursor.y) == initial_cursor
    assert terminal.board.blitter.current_buffer.get_line_text(0) == initial_text


def test_escape_to_csi_entry(terminal):
    """Test transition from ESCAPE to CSI_ENTRY state."""
    parser = Parser(terminal.board)
    parser.feed(f"{ESC}[")  # ESC then [


def test_ris_reset_terminal(terminal):
    """Test RIS (Reset to Initial State) sequence."""
    parser = Parser(terminal.board)

    # Write some content and move cursor
    parser.feed("Hello World")
    parser.feed(f"{ESC}[5;10H")  # Move cursor to 5,10
    initial_content = terminal.board.blitter.current_buffer.get_line_text(0)
    assert "Hello World" in initial_content
    assert terminal.board.cursor.y == 4  # 0-indexed
    assert terminal.board.cursor.x == 9  # 0-indexed

    # Send RIS
    parser.feed(f"{ESC}c")  # ESC then c

    # Should reset cursor and clear screen
    assert terminal.board.cursor.x == 0
    assert terminal.board.cursor.y == 0
    # Screen should be cleared
    cleared_content = terminal.board.blitter.current_buffer.get_line_text(0)
    assert cleared_content.strip() == ""


def test_ind_index(terminal):
    """Test IND (Index) sequence."""
    parser = Parser(terminal.board)
    initial_y = terminal.board.cursor.y

    parser.feed("\x1bD")  # ESC then D (IND - Index)

    # Should move cursor down one line
    assert terminal.board.cursor.y == initial_y + 1


def test_ri_reverse_index_no_scroll(terminal):
    """Test RI (Reverse Index) sequence without scrolling."""
    parser = Parser(terminal.board)

    # Move cursor down a few lines first
    parser.feed("\x1b[6H")  # Move to line 6 (1-indexed)
    assert terminal.board.cursor.y == 5  # 0-indexed

    # Send reverse index
    parser.feed("\x1bM")  # ESC then M (RI)

    # Should move cursor up one line
    assert terminal.board.cursor.y == 4


def test_ri_reverse_index_with_scroll(terminal):
    """Test RI (Reverse Index) sequence with scrolling."""
    parser = Parser(terminal.board)

    # Cursor should start at 0,0
    assert terminal.board.cursor.y == 0

    # Write some content
    parser.feed("Line 1")
    parser.feed("\r\n")
    parser.feed("Line 2")
    parser.feed("\x1b[1H")  # Move cursor to top

    # Send reverse index from top - should cause scroll
    parser.feed("\x1bM")  # ESC then M (RI)

    # Cursor should remain at top
    assert terminal.board.cursor.y == 0


def test_desc_save_cursor(terminal):
    """Test DECSC (Save Cursor) sequence."""
    parser = Parser(terminal.board)

    # Move cursor to a specific position
    parser.feed("\x1b[10;20H")  # Move to line 10, column 20
    assert terminal.board.cursor.y == 9  # 0-indexed
    assert terminal.board.cursor.x == 19  # 0-indexed

    # Save cursor
    parser.feed("\x1b7")  # ESC then 7 (DECSC)

    # Move cursor elsewhere
    parser.feed("\x1b[1;1H")  # Move to top-left
    assert terminal.board.cursor.y == 0
    assert terminal.board.cursor.x == 0


def test_decrc_restore_cursor(terminal):
    """Test DECRC (Restore Cursor) sequence."""
    parser = Parser(terminal.board)

    # Move and save cursor
    parser.feed("\x1b[5;15H")  # Move to specific position
    parser.feed("\x1b7")  # Save cursor

    # Move cursor elsewhere
    parser.feed("\x1b[20;5H")  # Move to different position
    assert terminal.board.cursor.y != 4
    assert terminal.board.cursor.x != 14

    # Restore cursor
    parser.feed("\x1b8")  # ESC then 8 (DECRC)

    # Should be back at saved position
    assert terminal.board.cursor.y == 4  # 0-indexed from line 5
    assert terminal.board.cursor.x == 14  # 0-indexed from column 15
