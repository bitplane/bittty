"""
bittty: A fast, pure Python terminal emulator library.

bittty (bitplane-tty) is a high-performance terminal emulator engine
that provides comprehensive ANSI sequence parsing and terminal state management.

Vocabulary: the `Board` is the machine (devices, registers, video memory, the
child process). A terminal (bittty.terminals) is the chrome a human looks at,
plugged into the board's display port. `Terminal` is deliberately not exported
here — import it from bittty.terminals.
"""

from .devices.board import Board
from .video import Video
from .parser import Parser
from .model import Model, XTERM, VT100, VT220, LINUX
from .operations import Operation, OperationSink
from .connections import Connection, DisplayPort, HostPort, Presentable
from .caps import TerminalCaps
from .style import (
    CURSOR_CODE,
    RESET_CODE,
)

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("bittty")
except PackageNotFoundError:
    __version__ = "unknown"

# Compat aliases — remove next release.
TerminalBoard = Board
Buffer = Video
Personality = Model
WritableTransport = Connection

__all__ = [
    "Board",
    "Video",
    "Buffer",
    "Parser",
    "Operation",
    "OperationSink",
    "HostPort",
    "DisplayPort",
    "Presentable",
    "TerminalCaps",
    "TerminalBoard",
    "Model",
    "Personality",
    "XTERM",
    "VT100",
    "VT220",
    "LINUX",
    "Connection",
    "WritableTransport",
    "CURSOR_CODE",
    "RESET_CODE",
]
