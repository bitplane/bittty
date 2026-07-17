"""Test configuration and fixtures."""

import pytest


@pytest.fixture
def real_pty():
    """Create a real platform-appropriate PTY for testing."""
    from bittty import Board

    pty = Board.get_pty_handler(24, 80)
    yield pty
    pty.close()
