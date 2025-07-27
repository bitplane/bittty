"""
Stdio PTY implementation for stream mode.

This implementation handles reading from stdin and writing to stdout
while also managing a background PTY for process execution.
"""

from __future__ import annotations

import os
import asyncio
import subprocess
import logging
from typing import Optional, Dict, Any

from .base import PTYBase
from .. import constants

logger = logging.getLogger(__name__)


class StdioPTY(PTYBase):
    """PTY implementation for stdio stream mode."""

    def __init__(
        self,
        stdin: Any,
        stdout: Any,
        rows: int = constants.DEFAULT_TERMINAL_HEIGHT,
        cols: int = constants.DEFAULT_TERMINAL_WIDTH,
    ):
        super().__init__(rows, cols)
        self.stdin = stdin
        self.stdout = stdout
        self._background_pty = None
        self._stdin_reader_task = None

    def _get_background_pty(self):
        """Get or create the background PTY for process execution."""
        if self._background_pty is None:
            # Import here to avoid circular imports
            import sys

            if sys.platform == "win32":
                from .windows import WindowsPTY

                self._background_pty = WindowsPTY(self.rows, self.cols)
            else:
                from .unix import UnixPTY

                self._background_pty = UnixPTY(self.rows, self.cols)
        return self._background_pty

    def read(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Read data from the background PTY and write to stdout."""
        if self._closed:
            return ""
        data = self._get_background_pty().read(size)
        if data and self.stdout:
            self.stdout.write(data)
            self.stdout.flush()
        return data

    def write(self, data: str) -> int:
        """Write data to the background PTY."""
        if self._closed:
            return 0
        return self._get_background_pty().write(data)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the background PTY."""
        self.rows = rows
        self.cols = cols
        if self._background_pty:
            self._background_pty.resize(rows, cols)

    def close(self) -> None:
        """Close the stdio PTY and background PTY."""
        if not self._closed:
            logger.info("Closing stdio PTY")

            # Cancel stdin reader task
            if self._stdin_reader_task and not self._stdin_reader_task.done():
                self._stdin_reader_task.cancel()
                self._stdin_reader_task = None

            # Close background PTY
            if self._background_pty:
                self._background_pty.close()
                self._background_pty = None

            self._closed = True

    def spawn_process(self, command: str, env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
        """Spawn a process attached to the background PTY and start stdin reading."""
        if self._closed:
            raise OSError("PTY is closed")

        logger.info("Starting terminal in stream mode")

        # Spawn process on background PTY
        background_pty = self._get_background_pty()
        process = background_pty.spawn_process(command, env)

        # Store process reference
        self._process = process

        # Start async stdin reader task
        self._stdin_reader_task = asyncio.create_task(self._async_read_from_stdin())

        logger.info(f"Spawned process in stream mode: pid={process.pid}")
        return process

    def set_nonblocking(self) -> None:
        """Set the background PTY to non-blocking mode."""
        if self._background_pty:
            self._background_pty.set_nonblocking()

    async def read_async(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Async read from the background PTY and write to stdout."""
        if self._closed:
            return ""
        if self._background_pty:
            data = await self._background_pty.read_async(size)
            if data and self.stdout:
                self.stdout.write(data)
                self.stdout.flush()
            return data
        return ""

    def flush(self) -> None:
        """Flush the background PTY and stdout."""
        if self._closed:
            return

        if self._background_pty:
            self._background_pty.flush()

        if self.stdout:
            try:
                self.stdout.flush()
            except Exception:
                pass

    async def _async_read_from_stdin(self) -> None:
        """Async task to read from stdin and forward to the background PTY."""
        loop = asyncio.get_running_loop()

        def read_stdin():
            try:
                # Read available data from stdin
                data = os.read(self.stdin.fileno(), 1024)
                return data.decode("utf-8", errors="replace")
            except (OSError, IOError):
                return ""

        try:
            while not self._closed and self._background_pty:
                # Read from stdin in a thread to avoid blocking
                data = await loop.run_in_executor(None, read_stdin)
                if not data:
                    await asyncio.sleep(0.01)  # Small delay if no data
                    continue

                # Forward input directly to background PTY
                try:
                    self._background_pty.write(data)
                except UnicodeDecodeError:
                    pass

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Error reading from stdin: {e}")
