"""Style operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation
from ..style import Style, parse_sgr_sequence, style_to_ansi

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class StyleDevice:
    """Applies style operations to the current Terminal implementation."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal

    def handle_operation(self, operation: Operation) -> None:
        if operation.name == "SGR":
            style, reset = operation.args
            if reset:
                self.terminal.current_ansi_code = style_to_ansi(style)
                return

            current_style = (
                parse_sgr_sequence(self.terminal.current_ansi_code) if self.terminal.current_ansi_code else Style()
            )
            self.terminal.current_ansi_code = style_to_ansi(current_style.merge(style))
            return

        logger.debug("Unknown style operation: %s", operation)
