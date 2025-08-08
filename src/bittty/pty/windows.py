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

    def read(self, size: int = -1) -> str:
        """Read data as strings."""
        data = self.pty.read(size)
        return data or ""

    def write(self, data: str) -> int:
        """Write string data."""
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
    """Windows PTY implementation using pywinpty.

    Note: This PTY operates in text mode - winpty handles UTF-8 internally.
    The read/write methods work directly with strings for performance,
    with bytes conversion only when needed for compatibility.
    """

    def __init__(self, rows: int = constants.DEFAULT_TERMINAL_HEIGHT, cols: int = constants.DEFAULT_TERMINAL_WIDTH):
        if not winpty:
            raise OSError("pywinpty not installed. Install with: pip install textual-terminal[windows]")

        self._pty = winpty.PTY(cols, rows)

        # Wrap winpty in file-like interface for base class
        wrapper = WinptyFileWrapper(self._pty)
        super().__init__(wrapper, wrapper, rows, cols)

    def read(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Read data directly from winpty (text mode, no UTF-8 splitting needed)."""
        if self.closed:
            return ""
        return self.from_process.read(size)

    def write(self, data: str) -> int:
        """Write string data directly to winpty (text mode)."""
        if self.closed:
            return 0
        return self.to_process.write(data)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal."""
        super().resize(rows, cols)
        self._pty.set_size(cols, rows)

    def spawn_process(self, command: str, env: Optional[Dict[str, str]] = ENV) -> subprocess.Popen:
        """Spawn a process attached to this PTY."""
        if self.closed:
            raise OSError("PTY is closed")

        # Convert env dict to winpty format: null-separated "KEY=VALUE" string
        if env:
            env_strs = []
            for key, value in env.items():
                env_strs.append(f"{key}={value}")
            env_string = "\0".join(env_strs) + "\0"
        else:
            env_string = ""

        self._pty.spawn(command, env=env_string)

        # Return a process-like object that provides compatibility with subprocess.Popen
        process = WinptyProcessWrapper(self._pty)
        # Store process reference for cleanup
        self._process = process
        return process
