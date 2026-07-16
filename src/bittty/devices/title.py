"""Title operation handler for the current Terminal state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Device

if TYPE_CHECKING:
    from .board import TerminalBoard


class TitleDevice(Device):
    """Owns terminal title state and applies title operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.title = "Terminal"
        self.icon_title = "Terminal"
        self._stack: list[tuple[str, str]] = []
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

    def push(self) -> None:
        """XTWINOPS 22 — save the current window and icon titles."""
        self._stack.append((self.title, self.icon_title))

    def pop(self) -> None:
        """XTWINOPS 23 — restore the most recently saved titles."""
        if self._stack:
            self.title, self.icon_title = self._stack.pop()
