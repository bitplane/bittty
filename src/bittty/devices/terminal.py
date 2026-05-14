"""Compatibility adapter for parser operation sinks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..operations import Operation
from .board import TerminalBoard

if TYPE_CHECKING:
    from ..terminal import Terminal


class TerminalOperationSink:
    """Compatibility wrapper around the terminal board."""

    def __init__(self, terminal: Terminal) -> None:
        self.board = terminal.board if hasattr(terminal, "board") else TerminalBoard(terminal)

    def __getattr__(self, name: str):
        return getattr(self.board, name)

    def handle_operation(self, operation: Operation) -> None:
        self.board.handle_operation(operation)
