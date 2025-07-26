from bittty.parser import Parser
from bittty.constants import ESC
from bittty.terminal import Terminal


def test_csi_cup_cursor_position(standard_terminal: Terminal):
    """Test CSI H (CUP - Cursor Position) with parameters."""
    parser = Parser(standard_terminal)
    parser.feed(f"{ESC}[10;20H")  # ESC[10;20H -> move to row 10, col 20
    assert standard_terminal.cursor_x == 19  # 0-based
    assert standard_terminal.cursor_y == 9  # 0-based


def test_csi_cup_cursor_position_no_params(standard_terminal: Terminal):
    """Test CSI H (CUP) with no parameters (defaults to 1;1)."""
    parser = Parser(standard_terminal)
    parser.feed(f"{ESC}[H")  # ESC[H -> move to row 1, col 1
    assert standard_terminal.cursor_x == 0
    assert standard_terminal.cursor_y == 0


def test_csi_cuu_cursor_up(standard_terminal: Terminal):
    """Test CSI A (CUU - Cursor Up) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.cursor_y = 10
    parser.feed(f"{ESC}[5A")  # ESC[5A -> move up 5 rows
    assert standard_terminal.cursor_y == 5


def test_csi_cuu_cursor_up_no_param(standard_terminal: Terminal):
    """Test CSI A (CUU) with no parameter (defaults to 1)."""
    parser = Parser(standard_terminal)
    standard_terminal.cursor_y = 10
    parser.feed(f"{ESC}[A")  # ESC[A -> move up 1 row
    assert standard_terminal.cursor_y == 9


def test_csi_cud_cursor_down(standard_terminal: Terminal):
    """Test CSI B (CUD - Cursor Down) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.cursor_y = 10
    parser.feed(f"{ESC}[5B")  # ESC[5B -> move down 5 rows
    assert standard_terminal.cursor_y == 15


def test_csi_cuf_cursor_forward(standard_terminal: Terminal):
    """Test CSI C (CUF - Cursor Forward) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.cursor_x = 10
    parser.feed("\x1b[5C")  # ESC[5C -> move forward 5 columns
    assert standard_terminal.cursor_x == 15


def test_csi_cub_cursor_backward(standard_terminal: Terminal):
    """Test CSI D (CUB - Cursor Backward) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.cursor_x = 10
    parser.feed("\x1b[5D")  # ESC[5D -> move backward 5 columns
    assert standard_terminal.cursor_x == 5


def test_csi_ed_erase_in_display(standard_terminal: Terminal):
    """Test CSI J (ED - Erase in Display) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.write_text("text")
    parser.feed("\x1b[2J")  # ESC[2J -> clear entire screen
    content = "".join("".join(char for _, char in line) for line in standard_terminal.get_content())
    assert content.strip() == ""
    assert standard_terminal.cursor_x == 0
    assert standard_terminal.cursor_y == 0


def test_csi_el_erase_in_line(standard_terminal: Terminal):
    """Test CSI K (EL - Erase in Line) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.write_text("some text")
    standard_terminal.cursor_x = 4
    parser.feed("\x1b[0K")  # ESC[0K -> clear from cursor to end of line
    line = "".join(char for _, char in standard_terminal.current_buffer.get_content()[0])
    assert line.startswith("some")
    assert line.strip() == "some"


def test_csi_ich_insert_characters(standard_terminal: Terminal):
    """Test CSI @ (ICH - Insert Characters) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.write_text("abcdef")
    standard_terminal.cursor_x = 2
    parser.feed("\x1b[3@")  # ESC[3@ -> insert 3 spaces
    line = "".join(char for _, char in standard_terminal.current_buffer.get_content()[0])
    assert line.startswith("ab   cde")


def test_csi_dch_delete_characters(standard_terminal: Terminal):
    """Test CSI P (DCH - Delete Characters) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.write_text("abcdef")
    standard_terminal.cursor_x = 2
    parser.feed("\x1b[2P")  # ESC[2P -> delete 2 characters
    line = "".join(char for _, char in standard_terminal.current_buffer.get_content()[0])
    assert line.startswith("abef")


def test_csi_il_insert_lines(standard_terminal: Terminal):
    """Test CSI L (IL - Insert Lines) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.write_text("line 1")
    standard_terminal.line_feed()
    standard_terminal.write_text("line 2")
    standard_terminal.cursor_y = 0
    parser.feed("\x1b[2L")  # ESC[2L -> insert 2 lines
    content = standard_terminal.get_content()
    assert "".join(char for _, char in content[0]).isspace()
    assert "".join(char for _, char in content[1]).isspace()
    assert "".join(char for _, char in content[2]).strip() == "line 1"


def test_csi_dl_delete_lines(standard_terminal: Terminal):
    """Test CSI M (DL - Delete Lines) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.write_text("line 1")
    standard_terminal.line_feed()
    standard_terminal.write_text("line 2")
    standard_terminal.line_feed()
    standard_terminal.write_text("line 3")
    standard_terminal.cursor_y = 0
    parser.feed("\x1b[2M")  # ESC[2M -> delete 2 lines
    content = standard_terminal.get_content()
    assert "".join(char for _, char in content[0]).strip() == "line 3"


def test_csi_su_scroll_up(standard_terminal: Terminal):
    """Test CSI S (SU - Scroll Up) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.write_text("line 1")
    parser.feed("\x1b[1S")  # ESC[1S -> scroll up 1 line
    content = standard_terminal.get_content()
    assert "".join(char for _, char in content[0]).isspace()


def test_csi_sd_scroll_down(standard_terminal: Terminal):
    """Test CSI T (SD - Scroll Down) with parameter."""
    parser = Parser(standard_terminal)
    standard_terminal.write_text("line 1")
    standard_terminal.line_feed()
    standard_terminal.write_text("line 2")
    parser.feed("\x1b[1T")  # ESC[1T -> scroll down 1 line
    content = standard_terminal.get_content()
    assert "".join(char for _, char in content[0]).isspace()
    assert "".join(char for _, char in content[1]).strip() == "line 1"


def test_csi_decstbm_set_scroll_region(standard_terminal: Terminal):
    """Test CSI r (DECSTBM - Set Top and Bottom Margins) with parameters."""
    parser = Parser(standard_terminal)
    parser.feed("\x1b[5;15r")  # ESC[5;15r -> set scroll region from row 5 to 15
    assert standard_terminal.scroll_top == 4
    assert standard_terminal.scroll_bottom == 14


def test_csi_cha_cursor_horizontal_absolute(standard_terminal: Terminal):
    """Test CSI G (CHA - Cursor Horizontal Absolute) with parameter."""
    parser = Parser(standard_terminal)
    parser.feed("\x1b[10G")  # ESC[10G -> move cursor to column 10
    assert standard_terminal.cursor_x == 9  # 0-based


def test_csi_vpa_vertical_position_absolute(standard_terminal: Terminal):
    """Test CSI d (VPA - Vertical Position Absolute) with parameter."""
    parser = Parser(standard_terminal)
    parser.feed("\x1b[5d")  # ESC[5d -> move cursor to row 5
    assert standard_terminal.cursor_y == 4  # 0-based


def test_csi_ech_erase_character(standard_terminal: Terminal):
    """Test CSI X (ECH - Erase Character)."""
    parser = Parser(standard_terminal)
    standard_terminal.write_text("before-text-after")
    standard_terminal.cursor_x = 7
    parser.feed("\x1b[4X")  # Erase 4 characters
    line = "".join(char for _, char in standard_terminal.current_buffer.get_content()[0])
    assert "before-    -after" in line


def test_csi_decsc_and_decrc_save_restore_cursor(standard_terminal: Terminal):
    """Test CSI s (DECSC) and CSI u (DECRC) for saving and restoring cursor."""
    parser = Parser(standard_terminal)
    standard_terminal.cursor_x = 15
    standard_terminal.cursor_y = 10
    parser.feed("\x1b[s")  # Save cursor
    standard_terminal.cursor_x = 0
    standard_terminal.cursor_y = 0
    parser.feed("\x1b[u")  # Restore cursor
    assert standard_terminal.cursor_x == 15
    assert standard_terminal.cursor_y == 10


def test_csi_truly_unhandled_sequences(standard_terminal: Terminal):
    """Test that truly unhandled CSI sequences are consumed and do not crash."""
    parser = Parser(standard_terminal)

    unhandled_sequences = [
        "\x1b[1p",  # Device status queries
        "\x1b[2t",  # Window operations
        "\x1b[3^",  # Privacy Message
        "\x1b[6n",  # Device Status Report / Cursor Position Report
        "\x1b[c",  # Device Attributes
    ]

    for seq in unhandled_sequences:
        standard_terminal.write_text("before")
        parser.feed(seq)
        standard_terminal.write_text("after")
        line = "".join(char for _, char in standard_terminal.current_buffer.get_content()[0])
        assert "beforeafter" in line.strip()
        standard_terminal.clear_screen(2)  # Clear screen for next test
