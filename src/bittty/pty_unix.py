"""
Unix/Linux/macOS PTY implementation.

This module provides PTY functionality for Unix-like systems.
"""

from __future__ import annotations

import os
import pty
import termios
import struct
import fcntl
import signal
import asyncio
import subprocess
from typing import Optional, Dict

from .pty_base import PTYBase
from . import constants
from .log import measure_performance, info


class UnixPTY(PTYBase):
    """Unix/Linux/macOS PTY implementation."""

    def __init__(self, rows: int = constants.DEFAULT_TERMINAL_HEIGHT, cols: int = constants.DEFAULT_TERMINAL_WIDTH):
        super().__init__(rows, cols)
        self.master_fd, self.slave_fd = pty.openpty()
        info(f"Created PTY: master_fd={self.master_fd}, slave_fd={self.slave_fd}")
        self.resize(rows, cols)

    @measure_performance("UnixPTY")
    def read(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Read data from the PTY."""
        if self._closed:
            return ""
        try:
            data = os.read(self.master_fd, size)
            return data.decode("utf-8", errors="replace")
        except OSError as e:
            if e.errno in (constants.EBADF, constants.EINVAL):
                self._closed = True
                raise
            return ""

    @measure_performance("UnixPTY")
    def write(self, data: str) -> int:
        """Write data to the PTY."""
        if self._closed:
            return 0
        try:
            return os.write(self.master_fd, data.encode("utf-8"))
        except OSError:
            return 0

    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal using TIOCSWINSZ ioctl."""
        self.rows = rows
        self.cols = cols
        if self._closed:
            return

        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def close(self) -> None:
        """Close the PTY file descriptors."""
        if not self._closed:
            info(f"Closing PTY: master_fd={self.master_fd}, slave_fd={self.slave_fd}")

            # Send SIGHUP to process group (like a shell would)
            if self._process is not None:
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGHUP)
                    info(f"Sent SIGHUP to process group {os.getpgid(self._process.pid)}")
                except (OSError, AttributeError) as e:
                    info(f"Could not send SIGHUP to process group: {e}")

            # Remove from asyncio event loop first
            try:
                loop = asyncio.get_event_loop()
                if self.master_fd and isinstance(self.master_fd, int):
                    loop.remove_reader(self.master_fd)
                    info(f"Removed master_fd {self.master_fd} from event loop")
            except (RuntimeError, ValueError, OSError):
                # Event loop not running or fd not registered
                pass

            try:
                if self.master_fd and isinstance(self.master_fd, int):
                    os.close(self.master_fd)
            except OSError:
                pass
            try:
                if self.slave_fd and isinstance(self.slave_fd, int):
                    os.close(self.slave_fd)
            except OSError:
                pass
            self._closed = True

    def spawn_process(self, command: str, env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
        """Spawn a process attached to this PTY."""
        process_env = dict(os.environ)
        if env:
            process_env.update(env)

        # Add terminal environment variables
        process_env.update(
            {
                "TERM": "xterm-256color",
                # Don't set LINES/COLUMNS - let process discover size via ioctl
                # Setting these prevents ncurses from responding to SIGWINCH properly
            }
        )

        # Ensure UTF-8 locale if not already set
        if "LANG" not in process_env or "UTF-8" not in process_env.get("LANG", ""):
            process_env["LANG"] = "en_US.UTF-8"
        if "LC_ALL" not in process_env:
            process_env["LC_ALL"] = process_env.get("LANG", "en_US.UTF-8")

        def preexec_fn():
            """Set up the child process to use PTY as controlling terminal."""
            # Create new session and become process group leader
            os.setsid()

            # Make the PTY the controlling terminal
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        process = subprocess.Popen(
            command if isinstance(command, list) else [command],
            shell=False,
            stdin=self.slave_fd,
            stdout=self.slave_fd,
            stderr=self.slave_fd,
            preexec_fn=preexec_fn,
            env=process_env,
        )

        # Close slave fd in parent (child has its own copy)
        os.close(self.slave_fd)
        self.slave_fd = None

        # Store process reference for cleanup
        self._process = process

        return process

    def set_nonblocking(self) -> None:
        """Set the PTY to non-blocking mode for async operations."""
        if self._closed:
            return
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    async def read_async(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Async read from PTY. Returns empty string when no data available."""
        if self._closed:
            return ""

        loop = asyncio.get_event_loop()
        try:
            # Use asyncio's add_reader for efficient async I/O
            future = loop.create_future()

            def read_ready():
                try:
                    data = os.read(self.master_fd, size)
                    loop.remove_reader(self.master_fd)
                    future.set_result(data.decode("utf-8", errors="replace"))
                except BlockingIOError:
                    loop.remove_reader(self.master_fd)
                    future.set_result("")
                except OSError as e:
                    loop.remove_reader(self.master_fd)
                    if e.errno in (constants.EBADF, constants.EINVAL):
                        self._closed = True
                    future.set_result("")

            loop.add_reader(self.master_fd, read_ready)
            return await future
        except Exception:
            return ""
