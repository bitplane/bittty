"""Shared fixtures for parser tests."""

import pytest
import io
from bittty.parser import Parser
from bittty import Board
from bittty.constants import DEFAULT_TERMINAL_WIDTH, DEFAULT_TERMINAL_HEIGHT


@pytest.fixture
def board():
    """Create a real Board with stdio streams for integration testing."""
    # Use StringIO streams for testing - Board creates StdioPTY internally
    stdin = io.StringIO()
    stdout = io.StringIO()

    term = Board(width=80, height=24, stdin=stdin, stdout=stdout)
    return term


@pytest.fixture
def parser(board):
    """Create a Parser attached to a real Board."""
    return Parser(board)


@pytest.fixture
def standard_board():
    """Return a real Board instance with standard dimensions.

    Use this fixture when testing end-to-end parser behavior,
    focusing on actual terminal content and state changes.
    """
    return Board(width=DEFAULT_TERMINAL_WIDTH, height=DEFAULT_TERMINAL_HEIGHT)


@pytest.fixture
def small_board():
    """Return a real Board instance with smaller dimensions for specific tests."""
    return Board(width=20, height=10)


@pytest.fixture
def parser_with_standard_board(standard_board):
    """Return a parser connected to a standard board for integration testing."""
    return Parser(standard_board), standard_board


@pytest.fixture
def parser_with_small_board(small_board):
    """Return a parser connected to a small board for specific test scenarios."""
    return Parser(small_board), small_board
