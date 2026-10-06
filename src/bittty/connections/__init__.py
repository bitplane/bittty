"""Connections and the board-side ports they plug into.

A port is a jack on the board, and both are full-duplex. The host port carries
bytes both ways (a serial line: PTY, pipe, socket). The display port carries
typed events both ways: present events down to the terminal (chrome), input
events up from it. The printer port carries bytes to whatever is on the
auxiliary cable.

- host: the Connection protocol and HostPort
- display: the Presentable and Screen protocols and DisplayPort
- printer: the PrinterConnection protocol, PrinterStatus and PrinterPort
- cables: connections that live in memory or on a stream
- recording: a tap that records the host line (asciicast v2), and a cable that replays one
- serial_line, printer_config: the settings a port offers its cable
"""

from .cables import InboundLine, MemoryConnection, MemoryPrinter, StreamPrinter
from .display import DisplayPort, Presentable, Screen
from .host import Connection, HostPort, LineTap
from .printer import PrinterConnection, PrinterPort, PrinterStatus
from .recording import Cast, CastRecorder, CastReplay

__all__ = [
    "Cast",
    "CastRecorder",
    "CastReplay",
    "Connection",
    "DisplayPort",
    "HostPort",
    "InboundLine",
    "LineTap",
    "MemoryConnection",
    "MemoryPrinter",
    "Presentable",
    "PrinterConnection",
    "PrinterPort",
    "PrinterStatus",
    "Screen",
    "StreamPrinter",
]
