"""Style operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation
from ..style import Style, get_background, parse_sgr_sequence, style_to_ansi

if TYPE_CHECKING:
    from .board import TerminalBoard

logger = logging.getLogger(__name__)


class StyleDevice:
    """Owns current style state and applies style operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.current = Style()

    @property
    def current_ansi_code(self) -> str:
        """The active style as an ANSI SGR string (boundary/compat accessor)."""
        return style_to_ansi(self.current)

    @current_ansi_code.setter
    def current_ansi_code(self, value: str) -> None:
        self.current = parse_sgr_sequence(value) if value else Style()

    def apply_sgr(self, style: Style, reset: bool = False) -> None:
        """Apply an SGR style update to the current style state."""
        self.current = style if reset else self.current.merge(style)

    def reset(self) -> None:
        """Reset to the default style."""
        self.current = Style()

    def background_ansi(self) -> str:
        """Return the active background style as ANSI."""
        return get_background(self.current_ansi_code)

    def handle_operation(self, operation: Operation) -> None:
        if operation.name == "SGR":
            style, reset = operation.args
            self.apply_sgr(style, reset)
            return

        logger.debug("Unknown style operation: %s", operation)
