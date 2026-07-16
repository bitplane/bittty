"""Style operation handler for the current Terminal state."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ..operations import Operation
from ..style import Style, get_background, parse_sgr_sequence, style_to_ansi

if TYPE_CHECKING:
    from .board import TerminalBoard


class StyleDevice:
    """Owns current style state and applies style operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.current = Style()
        self._monochrome = board.personality.color_depth == "monochrome"
        self.handlers = {
            "SGR": lambda op: self.apply_sgr(*op.args),
            "OSC_HYPERLINK": lambda op: self.set_hyperlink(op.args[0]),
        }

    @property
    def current_ansi_code(self) -> str:
        """The active style as an ANSI SGR string (boundary/compat accessor)."""
        return style_to_ansi(self.current)

    @current_ansi_code.setter
    def current_ansi_code(self, value: str) -> None:
        self.current = parse_sgr_sequence(value) if value else Style()

    def apply_sgr(self, style: Style, reset: bool = False) -> None:
        """Apply an SGR style update; a monochrome terminal drops colour attributes."""
        merged = style if reset else self.current.merge(style)
        # SGR (including reset) never affects the active hyperlink.
        merged = replace(merged, hyperlink=self.current.hyperlink)
        if self._monochrome:
            merged = replace(merged, fg=None, bg=None)
        self.current = merged

    def set_hyperlink(self, uri: str) -> None:
        """OSC 8 — start (non-empty URI) or end (empty) the active hyperlink."""
        self.current = replace(self.current, hyperlink=uri or None)

    def reset(self) -> None:
        """Reset to the default style."""
        self.current = Style()

    def background_ansi(self) -> str:
        """Return the active background style as ANSI."""
        return get_background(self.current_ansi_code)

    def handle_operation(self, operation: Operation) -> None:
        handler = self.handlers.get(operation.name)
        if handler is not None:
            handler(operation)
