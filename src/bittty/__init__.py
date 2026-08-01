"""A fast, pure Python terminal emulator library.

bittty provides ANSI/DEC sequence parsing, terminal state, and a headless cell grid.

Vocabulary: the `Board` is the machine (devices, registers, video memory, the
child process). A terminal (bittty.terminals) is the chrome a human looks at,
plugged into the board's display port. `Terminal` is deliberately not exported
here — import it from bittty.terminals.

Peripherals — simulations of hardware on the far end of a cable — are not exported
here either: import them from bittty.peripherals.<name>. Core never imports them.
"""

from importlib.metadata import PackageNotFoundError, version

from .caps import TerminalCaps
from .connections import (
    Connection,
    DisplayPort,
    HostPort,
    MemoryConnection,
    MemoryPrinter,
    Presentable,
    PrinterConnection,
    PrinterPort,
    PrinterStatus,
    StreamPrinter,
)
from .devices.board import Board
from .model import BITTTY, LINUX, VT100, VT220, VT510, XTERM, Model
from .operations import Operation, OperationSink
from .options import Option, PrinterCapabilities
from .parser import Parser
from .printer_config import PrinterConfiguration
from .style import (
    CURSOR_CODE,
    RESET_CODE,
)
from .video import Video
from .width import WidthPolicy

try:
    __version__ = version("bittty")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    "BITTTY",
    "CURSOR_CODE",
    "LINUX",
    "RESET_CODE",
    "VT100",
    "VT220",
    "VT510",
    "XTERM",
    "Board",
    "Connection",
    "DisplayPort",
    "HostPort",
    "MemoryConnection",
    "MemoryPrinter",
    "Model",
    "Operation",
    "OperationSink",
    "Option",
    "Parser",
    "Presentable",
    "PrinterCapabilities",
    "PrinterConfiguration",
    "PrinterConnection",
    "PrinterPort",
    "PrinterStatus",
    "StreamPrinter",
    "TerminalCaps",
    "Video",
    "WidthPolicy",
]
