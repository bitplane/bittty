"""
bittty: A fast, pure Python terminal emulator library.

bittty (bitplane-tty) is a high-performance terminal emulator engine
that provides comprehensive ANSI sequence parsing and terminal state management.
"""

from .terminal import Terminal
from .buffer import Buffer
from .parser import Parser
from .devices.board import TerminalBoard
from .personality import Personality, XTERM, VT100, VT220, LINUX
from .operations import Operation, OperationSink
from .transports import DisplayPort, HostPort, Presentable, WritableTransport
from .caps import DisplayCaps
from .frontends import Display
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
    "HostPort",
    "DisplayPort",
    "Presentable",
    "Display",
    "DisplayCaps",
    "TerminalBoard",
    "Personality",
    "XTERM",
    "VT100",
    "VT220",
    "LINUX",
    "WritableTransport",
    "CURSOR_CODE",
    "RESET_CODE",
]
