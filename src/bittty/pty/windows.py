"""
Windows PTY implementation using pywinpty.
"""

import subprocess
import logging
import time
from typing import Optional, Dict

try:
    import winpty
except ImportError:
    winpty = None

from .base import PTY, ENV
from .. import constants

logger = logging.getLogger(__name__)


class WinptyProcessWrapper:
    """Wrapper to provide subprocess.Popen-like interface for winpty PTY."""

    def __init__(self, pty):
        self.pty = pty
        self._returncode = None
        self._pid = None

    def poll(self):
        """Check if process is still running."""
        if self.pty.isalive():
            return None
        else:
            if self._returncode is None:
                self._returncode = constants.DEFAULT_EXIT_CODE
            return self._returncode

    def wait(self):
        """Wait for process to complete."""

        while self.pty.isalive():
            time.sleep(constants.PTY_POLL_INTERVAL)
        return self.poll()

    @property
    def returncode(self):
        """Get the return code."""
        return self.poll()

    @property
    def pid(self):
        """Get the process ID."""
        if self._pid is None and hasattr(self.pty, "pid"):
            self._pid = self.pty.pid
        return self._pid


class WindowsPTY(PTY):
    """Windows PTY implementation using pywinpty."""

    def __init__(self, rows: int = constants.DEFAULT_TERMINAL_HEIGHT, cols: int = constants.DEFAULT_TERMINAL_WIDTH):
        if not winpty:
            raise OSError("pywinpty not installed. Install with: pip install textual-terminal[windows]")

        self.pty = winpty.PTY(cols, rows)

        super().__init__(self.pty, self.pty, rows, cols)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal."""
        super().resize(rows, cols)
        self.pty.set_size(cols, rows)

    def read_bytes(self, size: int) -> bytes:
        """Read raw bytes from winpty."""
        data = self.pty.read(size)  # Returns str
        return data.encode("utf-8") if data else b""

    def write_bytes(self, data: bytes) -> int:
        """Write raw bytes to winpty."""
        text = data.decode("utf-8", errors="replace")
        return self.pty.write(text)

    def read(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Read string directly from winpty (no UTF-8 truncation issues)."""
        return self.pty.read(size) or ""

    def write(self, data: str) -> int:
        """Write string directly to winpty."""
        return self.pty.write(data)

    def spawn_process(self, command: str, env: Optional[Dict[str, str]] = ENV) -> subprocess.Popen:
        """Spawn a process attached to this PTY."""
        if self._closed:
            raise OSError("PTY is closed")

        self.pty.spawn(command, env=env)

        # Return a process-like object that provides compatibility with subprocess.Popen
        process = WinptyProcessWrapper(self.pty)
        # Store process reference for cleanup
        self._process = process
        return process
