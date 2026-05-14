"""Cursor operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class CursorDevice:
    """Owns cursor state and applies cursor operations."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal
        self.x = 0
        self.y = 0
        self.saved_x = 0
        self.saved_y = 0
        self.saved_ansi_code = ""

    def set_position(self, x: int | None, y: int | None) -> None:
        """Move cursor to a clamped terminal position."""
        if x is not None:
            self.x = max(0, min(x, self.terminal.width - 1))
        if y is not None:
            self.y = max(0, min(y, self.terminal.height - 1))

    def clamp_to_terminal(self) -> None:
        """Clamp the current position after terminal dimensions change."""
        self.set_position(self.x, self.y)

    def move_up(self, count: int) -> None:
        self.y = max(0, self.y - count)

    def move_down(self, count: int) -> None:
        self.y = min(self.terminal.height - 1, self.y + count)

    def move_forward(self, count: int) -> None:
        self.x = min(self.terminal.width - 1, self.x + count)

    def move_back(self, count: int) -> None:
        self.x = max(0, self.x - count)

    def save(self) -> None:
        """Save cursor position and attributes."""
        self.saved_x = self.x
        self.saved_y = self.y
        self.saved_ansi_code = self.terminal.current_ansi_code

    def restore(self) -> None:
        """Restore cursor position and attributes."""
        self.x = self.saved_x
        self.y = self.saved_y
        self.terminal.current_ansi_code = self.saved_ansi_code

    def handle_operation(self, operation: Operation) -> None:
        if operation.name in ("CUP", "HVP"):
            col, row = operation.args
            self.set_position(col, row)
            return
        if operation.name == "CUU":
            (count,) = operation.args
            self.move_up(count)
            return
        if operation.name == "CUD":
            (count,) = operation.args
            self.move_down(count)
            return
        if operation.name == "CUF":
            (count,) = operation.args
            self.move_forward(count)
            return
        if operation.name == "CUB":
            (count,) = operation.args
            self.move_back(count)
            return
        if operation.name == "CHA":
            (col,) = operation.args
            self.set_position(col, None)
            return
        if operation.name == "VPA":
            (row,) = operation.args
            self.set_position(None, row)
            return
        if operation.name == "SAVE":
            self.save()
            return
        if operation.name == "RESTORE":
            self.restore()
            return

        logger.debug("Unknown cursor operation: %s", operation)
