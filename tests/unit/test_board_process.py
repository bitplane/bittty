"""Board.start_process: the child it spawns, and what that child is told."""

import asyncio
import sys

import pytest

from bittty import Board
from bittty.model import KITTY, VT220, XTERM

pytestmark = [
    pytest.mark.unix,
    pytest.mark.skipif(sys.platform == "win32", reason="Unix PTY"),
    pytest.mark.asyncio,
]


async def _run(board: Board) -> str:
    """Start the child, wait for the board to reap it, and return the screen."""
    await board.start_process()
    for _ in range(500):
        if board.process is None:
            break
        await asyncio.sleep(0.01)
    return board.capture_text()


async def test_a_command_string_is_split_into_arguments():
    assert await _run(Board(command="printf hello")) == "hello"


@pytest.mark.parametrize(
    ("model", "term"),
    [(VT220, "vt220"), (XTERM, "xterm-256color"), (KITTY, "xterm-kitty")],
)
async def test_the_child_is_told_the_model_terminfo_name(model, term):
    board = Board(command="""sh -c 'printf %s "$TERM"'""", model=model)
    assert await _run(board) == term
