"""Connections and the board-side ports they plug into.

A port is a jack on the board, and both are full-duplex. The host port carries
bytes both ways (a serial line: PTY, pipe, socket). The display port carries
typed events both ways: present events down to the terminal (chrome), input
events up from it. The printer port carries bytes to whatever is on the
auxiliary cable.

- host: the Connection protocol and HostPort
- display: the Presentable protocol and DisplayPort
- printer: the PrinterConnection protocol, PrinterStatus and PrinterPort
- cables: connections that live in memory or on a stream
- serial_line, printer_config: the settings a port offers its cable
"""

from .cables import InboundLine, MemoryConnection, MemoryPrinter, StreamPrinter
from .display import DisplayPort, Presentable
from .host import Connection, HostPort
from .printer import PrinterConnection, PrinterPort, PrinterStatus

__all__ = [
    "Connection",
    "DisplayPort",
    "HostPort",
    "InboundLine",
    "MemoryConnection",
    "MemoryPrinter",
    "Presentable",
    "PrinterConnection",
    "PrinterPort",
    "PrinterStatus",
    "StreamPrinter",
]
