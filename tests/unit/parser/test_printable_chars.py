def test_printable_characters(parser, terminal):
    """Test that printable characters are written to the terminal."""
    parser.feed("Hello, World!")

    # Check that the text appears in the terminal buffer
    line_text = terminal.current_buffer.get_line_text(0)
    assert "Hello, World!" in line_text


def test_empty_feed(parser, terminal):
    """Test that feeding empty bytes doesn't break the parser."""
    parser.feed("")

    # Buffer should remain empty
    line_text = terminal.current_buffer.get_line_text(0)
    assert line_text.strip() == ""
