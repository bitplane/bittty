import pytest
from unittest.mock import Mock
from bittty.parser import Parser
from bittty.terminal import Terminal
from bittty.constants import BS, HT


@pytest.fixture
def screen():
    """Return a mock Screen object."""
    return Mock(spec=Terminal)


def test_backspace(screen):
    """Test that backspace moves the cursor back."""
    parser = Parser(screen)
    parser.feed(BS)
    screen.backspace.assert_called_once()


def test_horizontal_tab(screen):
    """Test that a horizontal tab moves the cursor to the next tab stop."""
    parser = Parser(screen)
    screen.cursor_x = 2
    screen.width = 80
    parser.feed(HT)
    assert screen.cursor_x == 8


def test_line_feed(screen):
    """Test that a line feed moves the cursor down."""
    parser = Parser(screen)
    parser.feed("\x0a")
    screen.line_feed.assert_called_once()


def test_carriage_return(screen):
    """Test that a carriage return moves the cursor to the beginning of the line."""
    parser = Parser(screen)
    parser.feed("\x0d")
    screen.carriage_return.assert_called_once()
