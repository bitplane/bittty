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
from .buffer import Buffer
from .parser import Parser
from .personality import Personality, XTERM, VT100, VT220, LINUX
from .operations import Operation, OperationSink
from .transports import DisplayPort, HostPort, Presentable, WritableTransport
from .caps import DisplayCaps
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

__all__ = [
    "Board",
    "Buffer",
    "Parser",
    "Operation",
    "OperationSink",
    "HostPort",
    "DisplayPort",
    "Presentable",
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
