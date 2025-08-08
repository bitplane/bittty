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


class WinptyFileWrapper:
    """File-like wrapper for winpty.PTY to work with base PTY class."""

    def __init__(self, winpty_pty):
        self.pty = winpty_pty

    def read(self, size: int = -1) -> bytes:
        """Read data as bytes."""
        data = self.pty.read(size)  # Returns bytes according to stub
        return data if data else b""

    def write(self, data: bytes) -> int:
        """Write bytes data."""
        # winpty.write() actually expects bytes according to stub but error suggests strings
        return self.pty.write(data)

    def close(self) -> None:
        """Close the PTY."""
        # winpty doesn't have explicit close, process death handles it
        pass

    @property
    def closed(self) -> bool:
        """Check if closed."""
        try:
            return not self.pty.isalive()
        except Exception:
            # If we can't check, assume it's not closed yet
            return False

    def flush(self) -> None:
        """Flush - no-op for winpty."""
        pass


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

        # Wrap winpty in file-like interface for base class
        wrapper = WinptyFileWrapper(self.pty)
        super().__init__(wrapper, wrapper, rows, cols)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal."""
        super().resize(rows, cols)
        self.pty.set_size(cols, rows)

    def spawn_process(self, command: str, env: Optional[Dict[str, str]] = ENV) -> subprocess.Popen:
        """Spawn a process attached to this PTY."""
        if self.closed:
            raise OSError("PTY is closed")

        self.pty.spawn(command, env=env)

        # Return a process-like object that provides compatibility with subprocess.Popen
        process = WinptyProcessWrapper(self.pty)
        # Store process reference for cleanup
        self._process = process
        return process
