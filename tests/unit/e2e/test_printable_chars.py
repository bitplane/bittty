def test_printable_characters(parser, board):
    """Test that printable characters are written to the terminal."""
    parser.feed("Hello, World!")

    # Check that the text appears on the page
    line_text = board.blitter.current_page.get_line_text(0)
    assert "Hello, World!" in line_text


def test_empty_feed(parser, board):
    """Test that feeding empty bytes doesn't break the parser."""
    parser.feed("")

    # The page should remain empty
    line_text = board.blitter.current_page.get_line_text(0)
    assert line_text.strip() == ""
