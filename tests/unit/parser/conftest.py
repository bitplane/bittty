"""Shared fixtures for parser tests."""

import pytest
from unittest.mock import Mock
from bittty.parser import Parser
from bittty.terminal import Terminal
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT


@pytest.fixture
def mock_terminal():
    """Return a mock Terminal object for isolated parser testing.

    Use this fixture when testing parser behavior in isolation,
    focusing on method calls and parameters rather than terminal state.
    """
    terminal = Mock(spec=Terminal)
    terminal.current_style = Mock()  # Mock the Style object
    terminal.width = DEFAULT_TERMINAL_WIDTH
    terminal.height = DEFAULT_TERMINAL_HEIGHT
    terminal.cursor_x = 0
    terminal.cursor_y = 0
    terminal.scroll_top = 0
    terminal.scroll_bottom = terminal.height - 1
    terminal.current_ansi_code = ""

    def _set_cursor(x, y):
        if x is not None:
            terminal.cursor_x = x
        if y is not None:
            terminal.cursor_y = y

    terminal.set_cursor.side_effect = _set_cursor
    return terminal


@pytest.fixture
def standard_terminal():
    """Return a real Terminal instance with standard dimensions.

    Use this fixture when testing end-to-end parser behavior,
    focusing on actual terminal content and state changes.
    """
    return Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)


@pytest.fixture
def small_terminal():
    """Return a real Terminal instance with smaller dimensions for specific tests."""
    return Terminal(width=20, height=10)


@pytest.fixture
def parser_with_mock_terminal(mock_terminal):
    """Return a parser connected to a mock terminal for isolated testing."""
    return Parser(mock_terminal), mock_terminal


@pytest.fixture
def parser_with_standard_terminal(standard_terminal):
    """Return a parser connected to a standard terminal for integration testing."""
    return Parser(standard_terminal), standard_terminal


@pytest.fixture
def parser_with_small_terminal(small_terminal):
    """Return a parser connected to a small terminal for specific test scenarios."""
    return Parser(small_terminal), small_terminal
