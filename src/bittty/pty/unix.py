"""
Unix/Linux/macOS PTY implementation.
"""

import os
import struct
import signal
import asyncio
import subprocess
import logging

try:
    import fcntl
    import pty
    import termios
except ImportError:
    pcntl = None
    pty = None
    termios = None

from .base import PTY, ENV
from .. import constants

logger = logging.getLogger(__name__)


UNIX_ENV = ENV | {"LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8")}


class UnixPTY(PTY):
    """Unix/Linux/macOS PTY implementation."""

    def __init__(self, rows: int = constants.DEFAULT_TERMINAL_HEIGHT, cols: int = constants.DEFAULT_TERMINAL_WIDTH):
        self.master_fd, self.slave_fd = pty.openpty()
        logger.info(f"Created PTY: master_fd={self.master_fd}, slave_fd={self.slave_fd}")

        # set non-blocking
        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Create a single file object for both reading and writing
        self.master_file = os.fdopen(self.master_fd, "rb+", buffering=0)

        # Initialize base class with file object
        super().__init__(self.master_file, self.master_file, rows, cols)

        self.resize(rows, cols)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal using TIOCSWINSZ ioctl."""
        super().resize(rows, cols)  # Update dimensions

        if self.closed:
            return

        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def close(self) -> None:
        """Close the PTY file descriptors."""
        if not self.closed:
            logger.info(f"Closing PTY: master_fd={self.master_fd}, slave_fd={self.slave_fd}")

            # Send SIGHUP to process group (like a shell would)
            if self._process is not None:
                try:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGHUP)
                    logger.info(f"Sent SIGHUP to process group {os.getpgid(self._process.pid)}")
                except (OSError, AttributeError) as e:
                    logger.info(f"Could not send SIGHUP to process group: {e}")

            # Remove from asyncio event loop first
            try:
                loop = asyncio.get_running_loop()
                if self.master_fd and isinstance(self.master_fd, int):
                    loop.remove_reader(self.master_fd)
                    logger.info(f"Removed master_fd {self.master_fd} from event loop")
            except (RuntimeError, ValueError, OSError):
                # Event loop not running or fd not registered
                pass

            # Close slave fd manually
            try:
                if self.slave_fd and isinstance(self.slave_fd, int):
                    os.close(self.slave_fd)
            except OSError:
                pass

            # Let base class close master_fd
            super().close()

    def spawn_process(self, command: str, env: dict[str, str] = UNIX_ENV) -> subprocess.Popen:
        """Spawn a process attached to this PTY."""

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
            env=env,
        )

        # Close slave fd in parent (child has its own copy)
        os.close(self.slave_fd)
        self.slave_fd = None

        # Store process reference for cleanup
        self._process = process

        return process

    def flush(self) -> None:
        """
        Flush output using os.fsync() for real PTY file descriptor.

        More efficient than generic flush() - ensures data is written through
        to the terminal device, not just buffered. Important for interactive
        terminal responsiveness.
        """
        os.fsync(self.master_fd)

    async def read_async(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """
        Async read from PTY using efficient file descriptor monitoring.

        Uses loop.add_reader() with file descriptors for maximum efficiency on Unix.
        This is the most performant approach since Unix supports select/poll on PTY fds.
        """
        if self.closed:
            return ""

        loop = asyncio.get_running_loop()
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
                        # Mark as closed by closing the file
                        self.master_file.close()
                    future.set_result("")

            loop.add_reader(self.master_fd, read_ready)
            return await future
        except Exception:
            return ""
