from bittty.parser import Parser, parse_csi_sequence, parse_string_sequence


def test_parse_csi_basic_sequences():
    """Test parsing of basic CSI sequences."""
    # Simple cursor position
    params, intermediates, final = parse_csi_sequence("\x1b[10;20H")
    assert params == [10, 20]
    assert intermediates == []
    assert final == "H"


def test_parse_csi_private_sequences():
    """Test parsing of private CSI sequences."""
    # Private mode setting
    params, intermediates, final = parse_csi_sequence("\x1b[?25h")
    assert params == [25]
    assert intermediates == ["?"]
    assert final == "h"


def test_parse_csi_with_intermediates():
    """Test parsing of CSI sequences with intermediate characters."""
    # Device attributes with > intermediate
    params, intermediates, final = parse_csi_sequence("\x1b[>0c")
    assert params == [0]
    assert intermediates == [">"]
    assert final == "c"


def test_parse_csi_empty_params():
    """Test parsing of CSI sequences with empty parameters."""
    params, intermediates, final = parse_csi_sequence("\x1b[;H")
    assert params == [None, None]
    assert intermediates == []
    assert final == "H"


def test_parse_osc_sequences():
    """Test parsing of OSC (Operating System Command) sequences."""
    # Window title
    content = parse_string_sequence("\x1b]2;My Title\x07", "osc")
    assert content == "2;My Title"

    # With ST terminator
    content = parse_string_sequence("\x1b]0;Title\x1b\\", "osc")
    assert content == "0;Title"


def test_parse_dcs_sequences():
    """Test parsing of DCS (Device Control String) sequences."""
    content = parse_string_sequence("\x1bPHello World\x1b\\", "dcs")
    assert content == "Hello World"


def test_mixed_escape_and_text_parsing(terminal):
    """Test parsing mixed escape sequences and text."""
    parser = Parser(terminal)

    # Mix of text, CSI, and text
    parser.feed("Hello \x1b[31mRed\x1b[0m World")

    # Should have written text and processed color changes
    text_content = terminal.current_buffer.get_line_text(0).strip()
    assert "Hello" in text_content
    assert "Red" in text_content
    assert "World" in text_content


def test_complete_sequence_processing(terminal):
    """Test that complete sequences are processed correctly."""
    parser = Parser(terminal)

    # Feed complete sequences
    parser.feed("\x1b[10;20H")  # Complete cursor position sequence (row;col format)

    # CUP format is row;column, so 10;20 means row 10, column 20 (0-based: y=9, x=19)
    assert terminal.cursor_y == 9  # row 10 -> y=9
    assert terminal.cursor_x == 19  # column 20 -> x=19

    # Test another complete sequence
    parser.feed("\x1b[5;10H")  # row 5, column 10
    assert terminal.cursor_y == 4  # row 5 -> y=4
    assert terminal.cursor_x == 9  # column 10 -> x=9
