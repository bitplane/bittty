"""
Base PTY interface for terminal emulation.

This module provides a concrete base class that works with file-like objects,
with platform-specific subclasses overriding only the byte-level I/O methods.
"""

import asyncio
from typing import Optional, BinaryIO
import subprocess
import codecs
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
        self._buffer = b""
        self._dec = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def read_bytes(self, size: int) -> bytes:
        """Read raw bytes. Override in subclasses for platform-specific I/O."""
        data = self.from_process.read(size)
        return data if data else b""

    def write_bytes(self, data: bytes) -> int:
        """Write raw bytes. Override in subclasses for platform-specific I/O."""
        return self.to_process.write(data) or 0

    def read(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Read data using the C incremental UTF-8 decoder (buffers split code points)."""
        b = self.read_bytes(size)
        if b:
            s = self._dec.decode(b, final=False)  # holds incomplete tails internally
            # expose undecoded tail for tests/inspection
            tail, _state = self._dec.getstate()  # tail is bytes of an incomplete seq (if any)
            self._buffer = tail
            return s
        else:
            # EOF / no new data: flush any incomplete sequence per 'replace' policy
            s = self._dec.decode(b"", final=True)
            self._dec.reset()
            self._buffer = b""
            return s

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
