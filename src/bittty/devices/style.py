"""Style operation handler for the current Terminal state."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from .base import Device
from ..style import Style, get_background, parse_sgr_sequence, style_to_ansi

if TYPE_CHECKING:
    from .board import TerminalBoard


class StyleDevice(Device):
    """Owns current style state and applies style operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.current = Style()
        self.default = Style()  # ESC[8]: the attributes SGR 0 resets to
        self.stack: list[Style] = []  # XTPUSHSGR / XTPOPSGR
        self._monochrome = board.personality.color_depth == "monochrome"
        self.handlers = {
            "SGR": lambda op: self.apply_sgr(*op.args),
            "OSC_HYPERLINK": lambda op: self.set_hyperlink(op.args[0]),
            "DECSCA": lambda op: self.set_protected(op.args[0]),
            "SPA": lambda op: self.set_protected(1),  # start protected area
            "EPA": lambda op: self.set_protected(0),  # end protected area
            "XTPUSHSGR": lambda op: self.stack.append(self.current),
            "XTPOPSGR": lambda op: self.pop_sgr(),
        }

    def pop_sgr(self) -> None:
        """XTPOPSGR — restore the SGR attributes saved by the matching XTPUSHSGR."""
        if self.stack:
            self.current = self.stack.pop()

    @property
    def current_ansi_code(self) -> str:
        """The active style as an ANSI SGR string (boundary/compat accessor)."""
        return style_to_ansi(self.current)

    @current_ansi_code.setter
    def current_ansi_code(self, value: str) -> None:
        self.current = parse_sgr_sequence(value) if value else Style()

    def apply_sgr(self, style: Style, reset: bool = False) -> None:
        """Apply an SGR style update; a monochrome terminal drops colour attributes."""
        merged = self.default if reset else self.current.merge(style)
        # SGR (including reset) never affects the active hyperlink or protection.
        merged = replace(merged, hyperlink=self.current.hyperlink, protected=self.current.protected)
        if self._monochrome:
            merged = replace(merged, fg=None, bg=None)
        self.current = merged

    def set_default(self) -> None:
        """ESC [ 8 ] — make the current attributes the default (the SGR 0 target)."""
        self.default = self.current

    def set_hyperlink(self, uri: str) -> None:
        """OSC 8 — start (non-empty URI) or end (empty) the active hyperlink."""
        self.current = replace(self.current, hyperlink=uri or None)

    def set_protected(self, mode: int) -> None:
        """DECSCA — 1 protects subsequent characters from selective erase; 0/2 clears it."""
        self.current = replace(self.current, protected=True if mode == 1 else None)

    def reset(self) -> None:
        """Reset to the default style (and clear the ESC[8] default register and SGR stack)."""
        self.current = Style()
        self.default = Style()
        self.stack = []

    def background_ansi(self) -> str:
        """Return the active background style as ANSI."""
        return get_background(self.current_ansi_code)
