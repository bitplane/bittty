"""
bittty: A fast, pure Python terminal emulator library.

bittty (bitplane-tty) is a high-performance terminal emulator engine
that provides comprehensive ANSI sequence parsing and terminal state management.

Vocabulary: the `Board` is the machine (devices, registers, video memory, the
child process). A terminal (bittty.terminals) is the chrome a human looks at,
plugged into the board's display port. `Terminal` is deliberately not exported
here — import it from bittty.terminals.
"""

from importlib.metadata import PackageNotFoundError, version

from .caps import TerminalCaps
from .connections import Connection, DisplayPort, HostPort, Presentable
from .devices.board import Board
from .model import LINUX, VT100, VT220, XTERM, Model
from .operations import Operation, OperationSink
from .parser import Parser
from .style import (
    CURSOR_CODE,
    RESET_CODE,
)
from .video import Video

try:
    __version__ = version("bittty")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "CURSOR_CODE",
    "LINUX",
    "RESET_CODE",
    "VT100",
    "VT220",
    "XTERM",
    "Board",
    "Connection",
    "DisplayPort",
    "HostPort",
    "Model",
    "Operation",
    "OperationSink",
    "Parser",
    "Presentable",
    "TerminalCaps",
    "Video",
]
