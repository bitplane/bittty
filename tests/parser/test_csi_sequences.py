from bittty.parser import Parser
from bittty.constants import ESC


def test_csi_cup_cursor_position(mock_terminal):
    """Test CSI H (CUP - Cursor Position) with parameters."""
    parser = Parser(mock_terminal)
    parser.feed(f"{ESC}[10;20H")  # ESC[10;20H -> move to row 10, col 20
    mock_terminal.set_cursor.assert_called_once_with(19, 9)  # 0-based


def test_csi_cup_cursor_position_no_params(mock_terminal):
    """Test CSI H (CUP) with no parameters (defaults to 1;1)."""
    parser = Parser(mock_terminal)
    parser.feed(f"{ESC}[H")  # ESC[H -> move to row 1, col 1
    mock_terminal.set_cursor.assert_called_once_with(0, 0)  # 0-based


def test_csi_cuu_cursor_up(mock_terminal):
    """Test CSI A (CUU - Cursor Up) with parameter."""
    parser = Parser(mock_terminal)
    mock_terminal.cursor_y = 10
    parser.feed(f"{ESC}[5A")  # ESC[5A -> move up 5 rows
    assert mock_terminal.cursor_y == 5


def test_csi_cuu_cursor_up_no_param(mock_terminal):
    """Test CSI A (CUU) with no parameter (defaults to 1)."""
    parser = Parser(mock_terminal)
    mock_terminal.cursor_y = 10
    parser.feed(f"{ESC}[A")  # ESC[A -> move up 1 row
    assert mock_terminal.cursor_y == 9


def test_csi_cud_cursor_down(mock_terminal):
    """Test CSI B (CUD - Cursor Down) with parameter."""
    parser = Parser(mock_terminal)
    mock_terminal.cursor_y = 10
    parser.feed(f"{ESC}[5B")  # ESC[5B -> move down 5 rows
    assert mock_terminal.cursor_y == 15


def test_csi_cuf_cursor_forward(mock_terminal):
    """Test CSI C (CUF - Cursor Forward) with parameter."""
    parser = Parser(mock_terminal)
    mock_terminal.cursor_x = 10
    parser.feed("\x1b[5C")  # ESC[5C -> move forward 5 columns
    assert mock_terminal.cursor_x == 15


def test_csi_cub_cursor_backward(mock_terminal):
    """Test CSI D (CUB - Cursor Backward) with parameter."""
    parser = Parser(mock_terminal)
    mock_terminal.cursor_x = 10
    parser.feed("\x1b[5D")  # ESC[5D -> move backward 5 columns
    assert mock_terminal.cursor_x == 5


def test_csi_ed_erase_in_display(mock_terminal):
    """Test CSI J (ED - Erase in Display) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[2J")  # ESC[2J -> clear entire screen
    mock_terminal.clear_screen.assert_called_once_with(2)


def test_csi_el_erase_in_line(mock_terminal):
    """Test CSI K (EL - Erase in Line) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[1K")  # ESC[1K -> clear from beginning of line to cursor
    mock_terminal.clear_line.assert_called_once_with(1)


def test_csi_ich_insert_characters(mock_terminal):
    """Test CSI @ (ICH - Insert Characters) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[5@")  # ESC[5@ -> insert 5 characters
    mock_terminal.insert_characters.assert_called_once_with(5, mock_terminal.current_ansi_code)


def test_csi_dch_delete_characters(mock_terminal):
    """Test CSI P (DCH - Delete Characters) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[3P")  # ESC[3P -> delete 3 characters
    mock_terminal.delete_characters.assert_called_once_with(3)


def test_csi_il_insert_lines(mock_terminal):
    """Test CSI L (IL - Insert Lines) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[2L")  # ESC[2L -> insert 2 lines
    mock_terminal.insert_lines.assert_called_once_with(2)


def test_csi_dl_delete_lines(mock_terminal):
    """Test CSI M (DL - Delete Lines) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[4M")  # ESC[4M -> delete 4 lines
    mock_terminal.delete_lines.assert_called_once_with(4)


def test_csi_su_scroll_up(mock_terminal):
    """Test CSI S (SU - Scroll Up) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[3S")  # ESC[3S -> scroll up 3 lines
    mock_terminal.scroll_up.assert_called_once_with(3)


def test_csi_sd_scroll_down(mock_terminal):
    """Test CSI T (SD - Scroll Down) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[2T")  # ESC[2T -> scroll down 2 lines
    mock_terminal.scroll_down.assert_called_once_with(2)


def test_csi_decstbm_set_scroll_region(mock_terminal):
    """Test CSI r (DECSTBM - Set Top and Bottom Margins) with parameters."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[5;15r")  # ESC[5;15r -> set scroll region from row 5 to 15
    mock_terminal.set_scroll_region.assert_called_once_with(4, 14)  # 0-based


def test_csi_cha_cursor_horizontal_absolute(mock_terminal):
    """Test CSI G (CHA - Cursor Horizontal Absolute) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[10G")  # ESC[10G -> move cursor to column 10
    assert mock_terminal.cursor_x == 9  # 0-based


def test_csi_vpa_vertical_position_absolute(mock_terminal):
    """Test CSI d (VPA - Vertical Position Absolute) with parameter."""
    parser = Parser(mock_terminal)
    parser.feed("\x1b[5d")  # ESC[5d -> move cursor to row 5
    assert mock_terminal.cursor_y == 4  # 0-based
