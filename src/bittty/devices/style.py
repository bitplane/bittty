"""Style operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation
from ..style import Style, get_background, parse_sgr_sequence, style_to_ansi

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class StyleDevice:
    """Owns current style state and applies style operations."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal
        self.current_ansi_code = ""

    def apply_sgr(self, style: Style, reset: bool = False) -> None:
        """Apply an SGR style update to the current style state."""
        if reset:
            self.current_ansi_code = style_to_ansi(style)
            return

        current_style = parse_sgr_sequence(self.current_ansi_code) if self.current_ansi_code else Style()
        self.current_ansi_code = style_to_ansi(current_style.merge(style))

    def reset(self) -> None:
        """Reset to the default style."""
        self.current_ansi_code = ""

    def background_ansi(self) -> str:
        """Return the active background style as ANSI."""
        return get_background(self.current_ansi_code)

    def handle_operation(self, operation: Operation) -> None:
        if operation.name == "SGR":
            style, reset = operation.args
            self.apply_sgr(style, reset)
            return

        logger.debug("Unknown style operation: %s", operation)
