"""
bittty: A fast, pure Python terminal emulator library.

bittty (bitplane-tty) is a high-performance terminal emulator engine
that provides comprehensive ANSI sequence parsing and terminal state management.
"""

from .terminal import Terminal
from .buffer import Buffer
from .parser import Parser
from .devices.terminal import TerminalOperationSink
from .operations import Operation, OperationSink
from .style import (
    CURSOR_CODE,
    RESET_CODE,
)

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("bittty")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "Terminal",
    "Buffer",
    "Parser",
    "Operation",
    "OperationSink",
    "TerminalOperationSink",
    "CURSOR_CODE",
    "RESET_CODE",
]
