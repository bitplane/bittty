"""Default terminal device adapter for parser operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation
from .charset import CharsetDevice
from .control import ControlDevice
from .cursor import CursorDevice
from .modes import ModeDevice
from .query import QueryDevice
from .screen import ScreenDevice
from .style import StyleDevice
from .title import TitleDevice

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class TerminalOperationSink:
    """Applies parser operations to the current Terminal implementation."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal
        self.control = ControlDevice(terminal)
        self.charset = terminal.charset if hasattr(terminal, "charset") else CharsetDevice(terminal)
        self.cursor = terminal.cursor if hasattr(terminal, "cursor") else CursorDevice(terminal)
        self.modes = terminal.modes if hasattr(terminal, "modes") else ModeDevice(terminal)
        self.query = QueryDevice(terminal, self.modes)
        self.screen = terminal.screen if hasattr(terminal, "screen") else ScreenDevice(terminal)
        self.style = terminal.style if hasattr(terminal, "style") else StyleDevice(terminal)
        self.title = terminal.title_device if hasattr(terminal, "title_device") else TitleDevice(terminal)

    def handle_operation(self, operation: Operation) -> None:
        if operation.kind == "text" and operation.name == "PRINT":
            self.screen.write_text(operation.args[0], self.style.current_ansi_code)
            return

        if operation.kind == "control":
            self.control.handle_operation(operation)
            return

        if operation.kind == "escape":
            self.charset.handle_escape_operation(operation)
            return

        if operation.kind == "charset":
            self.charset.handle_charset_operation(operation)
            return

        if operation.kind == "cursor":
            self.cursor.handle_operation(operation)
            return

        if operation.kind == "edit":
            self.screen.handle_edit_operation(operation)
            return

        if operation.kind == "screen":
            self.screen.handle_screen_operation(operation)
            return

        if operation.kind == "style":
            self.style.handle_operation(operation)
            return

        if operation.kind == "query":
            self.query.handle_operation(operation)
            return

        if operation.kind == "title":
            self.title.handle_operation(operation)
            return

        if operation.kind == "mode":
            self.modes.handle_operation(operation)
            return

        if operation.kind in ("csi", "osc", "dcs", "apc", "pm", "sos"):
            logger.debug("%s: %r", operation.name, operation.raw)
            return

        logger.debug("Unknown operation: %s", operation)
