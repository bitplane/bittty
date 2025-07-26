"""
Windows PTY implementation using pywinpty.

This module provides PTY functionality for Windows systems.
"""

from __future__ import annotations

import os
import asyncio
import subprocess
from typing import Optional, Dict

from .pty_base import PTYBase
from . import constants
from .log import measure_performance


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
        import time

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


class WindowsPTY(PTYBase):
    """Windows PTY implementation using pywinpty."""

    def __init__(self, rows: int = constants.DEFAULT_TERMINAL_HEIGHT, cols: int = constants.DEFAULT_TERMINAL_WIDTH):
        super().__init__(rows, cols)
        try:
            import winpty

            self.winpty = winpty
            self.pty = winpty.PTY(cols, rows)
        except ImportError:
            raise OSError("pywinpty not installed. Install with: pip install textual-terminal[windows]")

    @measure_performance("WindowsPTY")
    def read(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Read data from the PTY."""
        if self._closed:
            return ""
        try:
            data = self.pty.read(size)
            # winpty might return bytes or str, ensure we return str
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")
            return data or ""
        except Exception:
            return ""

    @measure_performance("WindowsPTY")
    def write(self, data: str) -> int:
        """Write data to the PTY."""
        if self._closed:
            return 0
        try:
            return self.pty.write(data)
        except Exception:
            return 0

    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal."""
        self.rows = rows
        self.cols = cols
        if not self._closed:
            try:
                self.pty.set_size(cols, rows)
            except Exception:
                pass

    def close(self) -> None:
        """Close the PTY."""
        if not self._closed:
            try:
                os.close(self.pty.fd)
            except Exception:
                pass
            self._closed = True

    def spawn_process(self, command: str, env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
        """Spawn a process attached to this PTY."""
        if self._closed:
            raise OSError("PTY is closed")

        # Set environment variables for the process
        if env:
            for key, value in env.items():
                os.environ[key] = value

        # Add terminal environment variables
        os.environ.update(
            {
                "TERM": "xterm-256color",
                # Don't set LINES/COLUMNS - let process discover size via ioctl
                # Setting these prevents ncurses from responding to SIGWINCH properly
            }
        )

        # Use winpty to spawn the process attached to the PTY
        # winpty.spawn expects a string, not bytes
        if isinstance(command, str):
            # For shell commands, use cmd.exe
            if command.strip().startswith(("cmd", "powershell", "pwsh")):
                spawn_command = command
            else:
                spawn_command = f'cmd.exe /c "{command}"'
        else:
            # If command is a list, join it
            spawn_command = " ".join(command) if isinstance(command, list) else str(command)

        self.pty.spawn(spawn_command)

        # Return a process-like object that provides compatibility with subprocess.Popen
        process = WinptyProcessWrapper(self.pty)
        # Store process reference for cleanup
        self._process = process
        return process

    def set_nonblocking(self) -> None:
        """Set the PTY to non-blocking mode for async operations."""
        # Windows PTYs handle non-blocking I/O differently
        # pywinpty already provides non-blocking behavior
        pass

    async def read_async(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Async read from PTY. Returns empty string when no data available."""
        if self._closed:
            return ""

        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, self.pty.read, size)
            if isinstance(data, bytes):
                return data.decode("utf-8", errors="replace")
            return data or ""
        except Exception:
            return ""
