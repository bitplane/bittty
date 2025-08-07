"""Shared fixtures for parser tests."""

import pytest
import io
from bittty.parser import Parser
from bittty.terminal import Terminal
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT


@pytest.fixture
def terminal():
    """Create a real Terminal with stdio streams for integration testing."""
    # Use StringIO streams for testing - Terminal creates StdioPTY internally
    stdin = io.StringIO()
    stdout = io.StringIO()

    term = Terminal(width=80, height=24, stdin=stdin, stdout=stdout)
    return term


@pytest.fixture
def parser(terminal):
    """Create a Parser attached to a real Terminal."""
    return Parser(terminal)


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
def parser_with_standard_terminal(standard_terminal):
    """Return a parser connected to a standard terminal for integration testing."""
    return Parser(standard_terminal), standard_terminal


@pytest.fixture
def parser_with_small_terminal(small_terminal):
    """Return a parser connected to a small terminal for specific test scenarios."""
    return Parser(small_terminal), small_terminal
