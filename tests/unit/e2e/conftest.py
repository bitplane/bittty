"""Shared fixtures for parser-to-board integration tests."""

import io

import pytest

from bittty.constants import DEFAULT_TERMINAL_HEIGHT, DEFAULT_TERMINAL_WIDTH
from bittty.parser import Parser
from bittty import Board


@pytest.fixture
def board():
    """Create a real Board with stdio streams for integration testing."""
    stdin = io.StringIO()
    stdout = io.StringIO()
    return Board(width=80, height=24, stdin=stdin, stdout=stdout)


@pytest.fixture
def parser(board):
    """Create a Parser attached to a real Board."""
    return Parser(board)


@pytest.fixture
def standard_board():
    """Return a real Board instance with standard dimensions."""
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
