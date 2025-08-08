"""Test UTF-8 handling in the parser."""


def test_split_utf8_character(parser, terminal):
    """Test that a split multi-byte UTF-8 character is handled correctly."""
    # A 3-byte UTF-8 character (e.g., a snowman ☃)
    snowman = "\u2603"
    encoded_snowman = snowman.encode("utf-8")

    # Feed the first byte of the character
    parser.feed(encoded_snowman[:1].decode("latin-1"))
    assert snowman not in terminal.capture_pane()

    # Feed the remaining bytes
    parser.feed(encoded_snowman[1:].decode("latin-1"))
    assert snowman in terminal.capture_pane()
