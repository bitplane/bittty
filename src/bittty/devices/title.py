"""Title operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class TitleDevice:
    """Applies title operations to the current Terminal implementation."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal

    def handle_operation(self, operation: Operation) -> None:
        (title,) = operation.args
        if operation.name == "SET_ICON_AND_WINDOW_TITLE":
            self.terminal.set_title(title)
            self.terminal.set_icon_title(title)
            return
        if operation.name == "SET_ICON_TITLE":
            self.terminal.set_icon_title(title)
            return
        if operation.name == "SET_WINDOW_TITLE":
            self.terminal.set_title(title)
            return

        logger.debug("Unknown title operation: %s", operation)
