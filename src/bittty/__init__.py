"""A fast, pure Python terminal emulator library.

bittty provides ANSI/DEC sequence parsing, terminal state, and a headless cell grid.

Vocabulary: the `Board` is the machine (devices, registers, video memory, the
child process). A terminal (bittty.terminals) is the chrome a human looks at,
plugged into the board's display port. `Terminal` is deliberately not exported
here — import it from bittty.terminals.
"""

from importlib.metadata import PackageNotFoundError, version

from .caps import TerminalCaps
from .connections import (
    Connection,
    DisplayPort,
    HostPort,
    Presentable,
    PrinterConnection,
    PrinterPort,
    PrinterStatus,
)
from .devices.board import Board
from .model import BITTTY, LINUX, VT100, VT220, VT510, XTERM, Model, PrinterCapabilities
from .operations import Operation, OperationSink
from .parser import Parser
from .printer_languages import (
    PrintDirection,
    PrinterCharacterSet,
    PrinterCharacterState,
    PrinterColor,
    PrinterDensity,
    PrinterLanguage,
    PrinterRendition,
    PrinterScript,
    PrinterUnderline,
    VirtualPrinterState,
)
from .printer_pages import (
    LETTER_PAGE_GEOMETRY,
    PRINT_UNITS_PER_INCH,
    PrinterControlToken,
    PrinterPage,
    PrinterPageGeometry,
    PrinterPageItem,
    PrinterRect,
    PrinterRenditionSpan,
    PrinterTextRun,
)
from .printers import (
    MemoryPrinter,
    PrintedDataType,
    PrinterConfiguration,
    PrinterFlowControl,
    PrinterFlowThreshold,
    PrinterParity,
    PrinterPortSelection,
    PrinterType,
    ProPrinterCodePage,
    StreamPrinter,
    VirtualPrinter,
)
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
    "LETTER_PAGE_GEOMETRY",
    "LINUX",
    "PRINT_UNITS_PER_INCH",
    "RESET_CODE",
    "VT100",
    "VT220",
    "VT510",
    "XTERM",
    "Board",
    "Connection",
    "DisplayPort",
    "HostPort",
    "MemoryPrinter",
    "Model",
    "Operation",
    "OperationSink",
    "Parser",
    "Presentable",
    "PrintDirection",
    "PrintedDataType",
    "PrinterCapabilities",
    "PrinterCharacterSet",
    "PrinterCharacterState",
    "PrinterColor",
    "PrinterConfiguration",
    "PrinterConnection",
    "PrinterControlToken",
    "PrinterDensity",
    "PrinterFlowControl",
    "PrinterFlowThreshold",
    "PrinterLanguage",
    "PrinterPage",
    "PrinterPageGeometry",
    "PrinterPageItem",
    "PrinterParity",
    "PrinterPort",
    "PrinterPortSelection",
    "PrinterRect",
    "PrinterRendition",
    "PrinterRenditionSpan",
    "PrinterScript",
    "PrinterStatus",
    "PrinterTextRun",
    "PrinterType",
    "PrinterUnderline",
    "ProPrinterCodePage",
    "StreamPrinter",
    "TerminalCaps",
    "Video",
    "VirtualPrinter",
    "VirtualPrinterState",
    "WidthPolicy",
]
