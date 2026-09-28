"""Title operation handler for the current board state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import re

from ..options import XTERM_EXTRAS
from ..present import TitleChanged
from .base import Device

if TYPE_CHECKING:
    from .board import Board

_HEX_LABEL = re.compile(r"(?:[0-9A-Fa-f]{2})*")
_TITLE_STACK_MAX = 10  # xterm's depth: XTWINOPS 22/23 address stack slots 1-10


class TitleDevice(Device):
    """Owns terminal title state and applies title operations."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.title = "Terminal"
        self.icon_title = "Terminal"
        self._stack: list[tuple[str, str]] = []
        self.handlers = {
            "SET_ICON_AND_WINDOW_TITLE": lambda op: self.set_both(op.args[0]),
            "SET_ICON_TITLE": lambda op: self.set_icon_title(op.args[0]),
            "SET_WINDOW_TITLE": lambda op: self.set_title(op.args[0]),
        }
        # xterm title modes: set in hex, query in hex, set in UTF-8, query in UTF-8. The UTF-8
        # pair changes nothing here: bittty's labels are always Unicode.
        self.modes = [False] * 4
        if XTERM_EXTRAS in board.model.provides:
            self.handlers["XTSMTITLE"] = lambda op: self._set_modes(op.args[0], True)
            self.handlers["XTRMTITLE"] = lambda op: self._set_modes(op.args[0], False)

    def _set_modes(self, params, value: bool) -> None:
        """XTSMTITLE/XTRMTITLE; with no parameters xterm 407 changes nothing."""
        for feature in params:
            if feature is not None and 0 <= feature <= 3:
                self.modes[feature] = value

    def _label(self, text: str) -> str | None:
        """A label as the host sent it: hex-decoded in that mode, where bad hex is refused."""
        if not self.modes[0]:
            return text
        if not _HEX_LABEL.fullmatch(text):
            return None
        return bytes.fromhex(text).decode("utf-8", "replace")

    def reported(self, label: str) -> str:
        """A label as XTWINOPS 20/21 report it: the UTF-8 bytes in hex in that mode."""
        return label.encode("utf-8").hex().upper() if self.modes[1] else label

    def reset(self, hard: bool = True) -> None:
        """RIS clears the title modes; DECSTR keeps them."""
        if hard:
            self.modes = [False] * 4

    def _notify(self) -> None:
        self.board.present(TitleChanged(self.title, self.icon_title))

    def set_title(self, title: str) -> None:
        """Set terminal title."""
        self._set_labels(title, window=True, icon=False)

    def set_icon_title(self, icon_title: str) -> None:
        """Set terminal icon title."""
        self._set_labels(icon_title, window=False, icon=True)

    def set_both(self, title: str) -> None:
        """Set both the window title and the icon title."""
        self._set_labels(title, window=True, icon=True)

    def _set_labels(self, text: str, *, window: bool, icon: bool) -> None:
        label = self._label(text)
        if label is None:
            return
        if window:
            self.title = label
        if icon:
            self.icon_title = label
        self._notify()

    def push(self) -> None:
        """XTWINOPS 22 — save the current window and icon titles."""
        if len(self._stack) >= _TITLE_STACK_MAX:
            self._stack.pop(0)  # evict the oldest rather than grow forever
        self._stack.append((self.title, self.icon_title))

    def pop(self) -> None:
        """XTWINOPS 23 — restore the most recently saved titles."""
        if self._stack:
            self.title, self.icon_title = self._stack.pop()
            self._notify()
