"""Title operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class TitleDevice:
    """Owns terminal title state and applies title operations."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal
        self.title = "Terminal"
        self.icon_title = "Terminal"

    def set_title(self, title: str) -> None:
        """Set terminal title."""
        self.title = title

    def set_icon_title(self, icon_title: str) -> None:
        """Set terminal icon title."""
        self.icon_title = icon_title

    def handle_operation(self, operation: Operation) -> None:
        (title,) = operation.args
        if operation.name == "SET_ICON_AND_WINDOW_TITLE":
            self.set_title(title)
            self.set_icon_title(title)
            return
        if operation.name == "SET_ICON_TITLE":
            self.set_icon_title(title)
            return
        if operation.name == "SET_WINDOW_TITLE":
            self.set_title(title)
            return

        logger.debug("Unknown title operation: %s", operation)
