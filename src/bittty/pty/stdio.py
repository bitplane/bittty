"""
A host cable whose far end is a pair of streams.

There is no child process: the stdin stream carries the host's output into the
board, and the board's replies and keystrokes go out on the stdout stream — a
terminal on the end of a pipe, the way one sits on the end of a serial line.
"""

import subprocess
from typing import BinaryIO

from .. import constants
from .base import PTY


class StdioPTY(PTY):
    """Plug a board's host port into two binary streams (e.g. sys.stdin.buffer, sys.stdout.buffer)."""

    def __init__(
        self,
        stdin: BinaryIO,
        stdout: BinaryIO,
        rows: int = constants.DEFAULT_TERMINAL_HEIGHT,
        cols: int = constants.DEFAULT_TERMINAL_WIDTH,
    ):
        super().__init__(stdin, stdout, rows, cols)
        self._ended = False

    def read_bytes(self, size: int) -> bytes:
        """Whatever has arrived (read1 never waits for a full buffer); end of input unplugs the receive side."""
        data = self.from_process.read1(size)
        self._ended = not data
        return data

    def spawn_process(self, command: str, env: dict[str, str] | None = None) -> subprocess.Popen | None:
        """The far end is already there: nothing to spawn."""
        return None

    def close(self) -> None:
        """Unplug the cable; the streams belong to whoever passed them in, so they stay open."""
        self._ended = True
        self.to_process.flush()

    @property
    def closed(self) -> bool:
        return self._ended or self.from_process.closed
