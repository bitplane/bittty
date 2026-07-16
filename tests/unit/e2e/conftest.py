"""Shared fixtures for parser-to-terminal integration tests."""

import io

import pytest

from bittty.constants import DEFAULT_TERMINAL_HEIGHT, DEFAULT_TERMINAL_WIDTH
from bittty.parser import Parser
from bittty.terminal import Terminal


@pytest.fixture
def terminal():
    """Create a real Terminal with stdio streams for integration testing."""
    stdin = io.StringIO()
    stdout = io.StringIO()
    return Terminal(width=80, height=24, stdin=stdin, stdout=stdout)


@pytest.fixture
def parser(terminal):
    """Create a Parser attached to a real Terminal."""
    return Parser(terminal.board)


@pytest.fixture
def standard_terminal():
    """Return a real Terminal instance with standard dimensions."""
    return Terminal(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)


@pytest.fixture
def small_terminal():
    """Return a real Terminal instance with smaller dimensions for specific tests."""
    return Terminal(width=20, height=10)


@pytest.fixture
def parser_with_standard_terminal(standard_terminal):
    """Return a parser connected to a standard terminal for integration testing."""
    return Parser(standard_terminal.board), standard_terminal


@pytest.fixture
def parser_with_small_terminal(small_terminal):
    """Return a parser connected to a small terminal for specific test scenarios."""
    return Parser(small_terminal.board), small_terminal
