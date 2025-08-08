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


def high_bits(byte: int) -> int:
    """how many bits are set on the right side of this byte?"""
    return 8 - ((~byte & 0xFF).bit_length())


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
        new_data = self.read_bytes(size)

        # deal with split UTF8 sequences
        data = self._buffer + new_data
        self._buffer = b""

        if not new_data:
            return data.decode("utf-8", errors="replace")

        end = len(data)

        # Check if last few bytes form valid UTF-8 sequence endings
        u1 = 0, high_bits(data[-1])  # Last byte: ASCII only
        u2 = 2, high_bits(data[-2]) if end > 1 else 0  # 2nd to last: ASCII or 2-byte start
        u3 = 3, high_bits(data[-3]) if end > 2 else 0  # 3rd to last: ASCII or 3-byte start

        for pos, (allowed, actual) in enumerate((u1, u2, u3)):
            if actual in (0, allowed):
                # Valid position - sequence is complete
                break
            elif actual != 1:
                # Not a continuation byte and not valid - split here
                end = end - pos - 1
                break
            # actual == 1 means continuation byte, keep checking

        self._buffer = data[end:]
        data = data[:end]

        return data.decode("utf-8", errors="replace")

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
