"""
Base PTY interface for terminal emulation.

This module provides a concrete base class that works with file-like objects,
with platform-specific subclasses overriding only the byte-level I/O methods.
"""

import asyncio
import os
import subprocess
from io import BytesIO
from typing import BinaryIO

from .. import constants

DEFAULT_TERM = "xterm-256color"


class PTY:
    """
    A generic PTY that lacks OS integration.

    Uses StringIO if no file handles are provided, and subprocess to handle its
    children.

    If you use this then you'll have to
    """

    def __init__(
        self,
        from_process: BinaryIO | None = None,
        to_process: BinaryIO | None = None,
        rows: int = constants.DEFAULT_TERMINAL_HEIGHT,
        cols: int = constants.DEFAULT_TERMINAL_WIDTH,
    ):
        """Initialize PTY with file-like input/output sources.

        Args:
            from_process: File-like object to read process output from (or None)
            to_process: File-like object to write user input to (or None)
            rows: Terminal height
            cols: Terminal width
        """
        self.from_process = from_process or BytesIO()
        self.to_process = to_process or BytesIO()
        self.rows = rows
        self.cols = cols
        self._process = None

    def read_bytes(self, size: int) -> bytes:
        """Read raw bytes. Override in subclasses for platform-specific I/O."""
        data = self.from_process.read(size)
        return data if data else b""

    def write_bytes(self, data: bytes) -> int:
        """Write raw bytes. Override in subclasses for platform-specific I/O."""
        return self.to_process.write(data) or 0

    def write(self, data: str) -> int:
        """Write string as UTF-8 bytes."""
        return self.write_bytes(data.encode("utf-8"))

    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal (base implementation just updates dimensions)."""
        self.rows = rows
        self.cols = cols

    def close(self) -> None:
        """Close the PTY streams."""
        self.from_process.close()
        if self.to_process != self.from_process:
            self.to_process.close()

    @property
    def closed(self) -> bool:
        """Check if PTY is closed."""
        return self.from_process.closed

    def environment(self, term: str = DEFAULT_TERM) -> dict[str, str]:
        """The child's environment: the caller's, with only what the terminal owns overridden.

        subprocess env= replaces wholesale, so a bare {"TERM": ...} would launch the
        child with *nothing else* — no HOME, no PATH.
        """
        return os.environ | {"TERM": term}

    def spawn_process(self, command: str, env: dict[str, str] | None = None) -> subprocess.Popen:
        """Spawn a process connected to PTY streams."""
        env = self.environment() if env is None else env
        return subprocess.Popen(
            command, shell=True, stdin=self.to_process, stdout=self.from_process, stderr=self.from_process, env=env
        )

    async def read_bytes_async(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> bytes:
        """Read raw bytes asynchronously without passing through the text decoder."""
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self.read_bytes, size)
        except Exception:
            return b""

    def flush(self) -> None:
        """Flush output."""
        self.to_process.flush()
