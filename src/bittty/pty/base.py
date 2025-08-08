"""
Base PTY interface for terminal emulation.

This module provides a concrete base class that works with file-like objects,
with platform-specific subclasses overriding only the byte-level I/O methods.
"""

import asyncio
from typing import Optional, BinaryIO
import subprocess
from io import BytesIO

from .. import constants

ENV = {"TERM": "xterm-256color"}


class PTY:
    """
    A generic PTY that lacks OS integration.

    Uses StringIO if no file handles are provided, and subprocess to handle its
    children.

    If you use this then you'll have to
    """

    def __init__(
        self,
        from_process: Optional[BinaryIO] = None,
        to_process: Optional[BinaryIO] = None,
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
        self._buffer = b""  # Buffer for incomplete UTF-8 sequences

    def read_bytes(self, size: int) -> bytes:
        """Read raw bytes. Override in subclasses for platform-specific I/O."""
        data = self.from_process.read(size)
        return data if data else b""

    def write_bytes(self, data: bytes) -> int:
        """Write raw bytes. Override in subclasses for platform-specific I/O."""
        return self.to_process.write(data) or 0

    def read(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Read data with UTF-8 buffering."""
        raw_data = self.read_bytes(size)
        if not raw_data:
            return ""

        # deal with split UTF8 sequences
        raw_data = self._buffer + raw_data
        utf8_split = len(raw_data) - 1
        while 0 <= utf8_split < (len(raw_data) - 4) and (raw_data[utf8_split] & 0x80):
            utf8_split -= 1

        self._buffer = raw_data[utf8_split:]
        raw_data = raw_data[:utf8_split]

        text = raw_data.decode("utf-8", errors="replace")
        return text

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

    def spawn_process(self, command: str, env: dict[str, str] = ENV) -> subprocess.Popen:
        """Spawn a process connected to PTY streams."""
        return subprocess.Popen(
            command, shell=True, stdin=self.to_process, stdout=self.from_process, stderr=self.from_process, env=env
        )

    async def read_async(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """
        Async read using thread pool executor.

        Uses loop.run_in_executor() as a generic cross-platform approach.
        Unix PTY overrides this with more efficient file descriptor monitoring.
        Windows and other platforms use this thread pool implementation.
        """
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, self.read, size)
        except Exception:
            return ""

    def flush(self) -> None:
        """Flush output."""
        self.to_process.flush()
