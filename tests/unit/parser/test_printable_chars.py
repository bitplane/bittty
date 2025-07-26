import pytest
from unittest.mock import Mock, call
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

    calls = [
        call("H", terminal.current_ansi_code),
        call("e", terminal.current_ansi_code),
        call("l", terminal.current_ansi_code),
        call("l", terminal.current_ansi_code),
        call("o", terminal.current_ansi_code),
        call(",", terminal.current_ansi_code),
        call(" ", terminal.current_ansi_code),
        call("W", terminal.current_ansi_code),
        call("o", terminal.current_ansi_code),
        call("r", terminal.current_ansi_code),
        call("l", terminal.current_ansi_code),
        call("d", terminal.current_ansi_code),
        call("!", terminal.current_ansi_code),
    ]
    terminal.write_text.assert_has_calls(calls)


def test_empty_feed(terminal):
    """Test that feeding empty bytes doesn't break the parser."""
    parser = Parser(terminal)
    parser.feed("")
    terminal.write_text.assert_not_called()
