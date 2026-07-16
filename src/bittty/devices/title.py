"""Title operation handler for the current Terminal state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..operations import Operation

if TYPE_CHECKING:
    from .board import TerminalBoard


class TitleDevice:
    """Owns terminal title state and applies title operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.title = "Terminal"
        self.icon_title = "Terminal"
        self.handlers = {
            "SET_ICON_AND_WINDOW_TITLE": lambda op: self.set_both(op.args[0]),
            "SET_ICON_TITLE": lambda op: self.set_icon_title(op.args[0]),
            "SET_WINDOW_TITLE": lambda op: self.set_title(op.args[0]),
        }

    def set_title(self, title: str) -> None:
        """Set terminal title."""
        self.title = title

    def set_icon_title(self, icon_title: str) -> None:
        """Set terminal icon title."""
        self.icon_title = icon_title

    def set_both(self, title: str) -> None:
        """Set both the window title and the icon title."""
        self.set_title(title)
        self.set_icon_title(title)

    def handle_operation(self, operation: Operation) -> None:
        handler = self.handlers.get(operation.name)
        if handler is not None:
            handler(operation)
