"""Shared fixtures for parser-to-terminal integration tests."""

import io

import pytest

from bittty.constants import DEFAULT_TERMINAL_HEIGHT, DEFAULT_TERMINAL_WIDTH
from bittty.parser import Parser
from bittty import Board


@pytest.fixture
def terminal():
    """Create a real Board with stdio streams for integration testing."""
    stdin = io.StringIO()
    stdout = io.StringIO()
    return Board(width=80, height=24, stdin=stdin, stdout=stdout)


@pytest.fixture
def parser(terminal):
    """Create a Parser attached to a real Board."""
    return Parser(terminal)


@pytest.fixture
def standard_terminal():
    """Return a real Board instance with standard dimensions."""
    return Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)


@pytest.fixture
def small_terminal():
    """Return a real Board instance with smaller dimensions for specific tests."""
    return Board(width=20, height=10)


@pytest.fixture
def parser_with_standard_terminal(standard_terminal):
    """Return a parser connected to a standard terminal for integration testing."""
    return Parser(standard_terminal), standard_terminal


@pytest.fixture
def parser_with_small_terminal(small_terminal):
    """Return a parser connected to a small terminal for specific test scenarios."""
    return Parser(small_terminal), small_terminal
