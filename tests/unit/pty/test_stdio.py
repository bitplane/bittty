"""StdioPTY: a host cable whose far end is a pair of streams, not a child process."""

import asyncio
import io
import os

import pytest

from bittty import Board
from bittty.pty import StdioPTY

pytestmark = pytest.mark.asyncio


async def _until(condition) -> None:
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


async def test_a_board_on_stdio_spawns_nothing():
    board = Board(stdin=io.BytesIO(b""), stdout=io.BytesIO())
    await board.start_process()
    assert isinstance(board.pty, StdioPTY)
    assert board.process is None


async def test_stdin_is_the_host_output_and_replies_go_to_stdout():
    stdout = io.BytesIO()
    board = Board(stdin=io.BytesIO("héllo\x1b[6n".encode()), stdout=stdout)
    await board.start_process()
    await _until(lambda: board.pty.closed)  # end of input unplugs the receive side
    assert board.capture_text() == "héllo"
    assert stdout.getvalue() == b"\x1b[1;6R"


async def test_keystrokes_go_to_stdout():
    stdout = io.BytesIO()
    board = Board(stdin=io.BytesIO(b""), stdout=stdout)
    await board.start_process()
    board.input("ls\r")
    assert stdout.getvalue() == b"ls\r"


async def test_a_live_pipe_is_read_as_it_arrives():
    read_fd, write_fd = os.pipe()
    with open(read_fd, "rb") as stdin:
        board = Board(stdin=stdin, stdout=io.BytesIO())
        await board.start_process()
        os.write(write_fd, b"first")
        await _until(lambda: board.capture_text() == "first")  # no EOF and no full buffer needed
        os.close(write_fd)
        await _until(lambda: board.pty.closed)
        board.stop_process()


async def test_unplugging_leaves_the_streams_open():
    stdin, stdout = io.BytesIO(b""), io.BytesIO()
    board = Board(stdin=stdin, stdout=stdout)
    await board.start_process()
    board.stop_process()
    assert board.pty is None
    assert not stdin.closed
    assert not stdout.closed
