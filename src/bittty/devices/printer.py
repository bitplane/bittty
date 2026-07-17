"""Printer device: the terminal's aux printer port (Media Copy / MC).

Historically a terminal had a printer hanging off its aux port; Media Copy
routed screen data to it. Here the printer is a board device with an
attachable *sink* — a callable taking a str, or any object with a write()
method (a file, an io.StringIO, a real printer driver). Unattached, printed
output is simply discarded, exactly like a terminal with no printer connected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..operations import Operation
from .base import Device

if TYPE_CHECKING:
    from .board import Board


class PrinterDevice(Device):
    """Owns printer state (controller/auto-print modes) and the output sink."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.sink = None  # a frontend attaches a file/StringIO/callable
        self.controller_mode = False  # CSI 5 i: printable output goes to the printer, not the screen
        self.auto_print = False  # CSI ? 5 i: each line prints as the cursor leaves it
        self.handlers = {
            "MC": self.media_copy,
            "DECMC": self.dec_media_copy,
        }

    def attach(self, sink) -> None:
        """Attach a printer sink: a callable(str), or an object with a write(str) method."""
        self.sink = sink

    def emit(self, text: str) -> None:
        """Send text to the attached sink, if any."""
        if self.sink is None:
            return
        writer = self.sink.write if hasattr(self.sink, "write") else self.sink
        writer(text)

    def media_copy(self, operation: Operation) -> None:
        """MC (CSI Ps i) — ANSI media copy."""
        ps = operation.args[0]
        if ps == 0:  # print the screen
            self.print_screen()
        elif ps == 5:  # enter printer controller mode
            self.controller_mode = True
        elif ps == 4:  # exit printer controller mode
            self.controller_mode = False

    def dec_media_copy(self, operation: Operation) -> None:
        """DEC MC (CSI ? Ps i) — auto-print and DEC print variants."""
        ps = operation.args[0]
        if ps == 1:  # print the cursor line
            self.print_line(self.board.cursor.y)
        elif ps == 4:  # auto-print off
            self.auto_print = False
        elif ps == 5:  # auto-print on
            self.auto_print = True
        elif ps in (10, 11):  # print screen / all pages (bittty has one page)
            self.print_screen()

    def print_screen(self) -> None:
        """Send the whole current screen to the printer, one line per row."""
        buffer = self.board.screen.current_buffer
        lines = [buffer.get_line_text(y).rstrip() for y in range(self.board.height)]
        self.emit("\n".join(lines) + "\n")

    def print_line(self, y: int) -> None:
        """Send a single row to the printer."""
        self.emit(self.board.screen.current_buffer.get_line_text(y).rstrip() + "\n")

    def reset(self, hard: bool = True) -> None:
        """Leave printer controller/auto-print modes; the attached sink is config, so it stays."""
        self.controller_mode = False
        self.auto_print = False
