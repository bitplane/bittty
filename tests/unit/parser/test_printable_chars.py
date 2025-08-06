import pytest
from unittest.mock import Mock
from bittty.parser import Parser
from bittty.terminal import Terminal


@pytest.fixture
def terminal():
    """Return a mock Screen object."""
    terminal = Mock(spec=Terminal)
    terminal.current_style = Mock()
    terminal.current_ansi_code = ""
    return terminal


def test_printable_characters(terminal):
    """Test that printable characters are written to the terminal."""
    parser = Parser(terminal)
    parser.feed("Hello, World!")

    # The new parser processes printable text in chunks for better performance
    terminal.write_text.assert_called_once_with("Hello, World!", terminal.current_ansi_code)


def test_empty_feed(terminal):
    """Test that feeding empty bytes doesn't break the parser."""
    parser = Parser(terminal)
    parser.feed("")
    terminal.write_text.assert_not_called()
