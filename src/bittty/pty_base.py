"""
Base PTY interface for terminal emulation.

This module defines the abstract interface that all platform-specific
PTY implementations must follow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Dict
import subprocess

from . import constants


class PTYBase(ABC):
    """Abstract base class for PTY implementations."""

    def __init__(self, rows: int = constants.DEFAULT_TERMINAL_HEIGHT, cols: int = constants.DEFAULT_TERMINAL_WIDTH):
        self.rows = rows
        self.cols = cols
        self._closed = False
        self._process = None

    @abstractmethod
    def read(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Read data from the PTY."""
        pass

    @abstractmethod
    def write(self, data: str) -> int:
        """Write data to the PTY."""
        pass

    @abstractmethod
    def resize(self, rows: int, cols: int) -> None:
        """Resize the terminal."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the PTY."""
        pass

    @property
    def closed(self) -> bool:
        """Check if PTY is closed."""
        return self._closed

    @abstractmethod
    def spawn_process(self, command: str, env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
        """Spawn a process attached to this PTY."""
        pass

    @abstractmethod
    def set_nonblocking(self) -> None:
        """Set the PTY to non-blocking mode for async operations."""
        pass

    @abstractmethod
    async def read_async(self, size: int = constants.DEFAULT_PTY_BUFFER_SIZE) -> str:
        """Async read from PTY. Returns empty string when no data available."""
        pass
