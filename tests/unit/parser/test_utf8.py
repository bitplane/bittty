"""Test UTF-8 handling through parser."""


def test_utf8_through_parser(parser, terminal):
    """Test that UTF-8 characters work correctly through the parser directly."""
    # Test data: toilet, plunger, poop emojis repeated
    test_string = "🚽🪠💩" * 10

    # Feed the complete Unicode string to the parser
    # This is what actually happens - PTY decodes bytes to Unicode
    parser.feed(test_string)

    # Verify all the emojis made it through intact
    output = terminal.capture_pane()
    assert "🚽🪠💩" * 10 in output
