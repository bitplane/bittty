"""Query operation handler for the current Terminal state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..operations import Operation

if TYPE_CHECKING:
    from .board import TerminalBoard


class QueryDevice:
    """Applies terminal query operations to the current Terminal implementation."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.modes = board.modes
        self.handlers = {
            "CPR": self.report_cursor_position,
            "DSR": self.report_device_status,
            "DA1": self.report_primary_device_attributes,
            "DA2": self.report_secondary_device_attributes,
            "DECRQM": self.report_mode_status,
        }

    def report_cursor_position(self, operation: Operation) -> None:
        row = self.board.cursor.y + 1
        col = self.board.cursor.x + 1
        self.board.host.write(f"\033[{row};{col}R", flush=True)

    def report_device_status(self, operation: Operation) -> None:
        self.board.host.write("\033[0n", flush=True)

    def report_primary_device_attributes(self, operation: Operation) -> None:
        self.board.host.write(self.board.personality.da1_response, flush=True)

    def report_secondary_device_attributes(self, operation: Operation) -> None:
        response = self.board.personality.da2_response
        if response is not None:
            self.board.host.write(response, flush=True)

    def report_mode_status(self, operation: Operation) -> None:
        mode, private = operation.args
        status = self.modes.get_private_mode_status(mode) if private else self.modes.get_ansi_mode_status(mode)
        prefix = "?" if private else ""
        self.board.host.write(f"\033[{prefix}{mode};{status}$y", flush=True)

    def handle_operation(self, operation: Operation) -> None:
        handler = self.handlers.get(operation.name)
        if handler is not None:
            handler(operation)
