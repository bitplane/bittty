"""Terminal device board/backplane."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation
from .charset import CharsetDevice
from .control import ControlDevice
from .cursor import CursorDevice
from .keyboard import KeyboardDevice
from .modes import ModeDevice
from .mouse import MouseDevice
from .query import QueryDevice
from .screen import ScreenDevice
from .style import StyleDevice
from .title import TitleDevice

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class TerminalBoard:
    """Hosts terminal devices and routes parser operations to them."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal

        self.charset = CharsetDevice(terminal)
        self.cursor = CursorDevice(terminal)
        self.keyboard = KeyboardDevice(terminal)
        self.modes = ModeDevice(terminal)
        self.mouse = MouseDevice(terminal)
        self.screen = ScreenDevice(terminal)
        self.style = StyleDevice(terminal)
        self.title = TitleDevice(terminal)

        self._attach_terminal_aliases()

        self.control = ControlDevice(terminal)
        self.query = QueryDevice(terminal, self.modes)

        self.devices = {
            "charset": self.charset,
            "control": self.control,
            "cursor": self.cursor,
            "keyboard": self.keyboard,
            "modes": self.modes,
            "mouse": self.mouse,
            "query": self.query,
            "screen": self.screen,
            "style": self.style,
            "title": self.title,
        }

    def _attach_terminal_aliases(self) -> None:
        """Expose current device slots through the legacy Terminal facade."""
        self.terminal.charset = self.charset
        self.terminal.cursor = self.cursor
        self.terminal.keyboard = self.keyboard
        self.terminal.modes = self.modes
        self.terminal.mouse = self.mouse
        self.terminal.screen = self.screen
        self.terminal.style = self.style
        self.terminal.title_device = self.title

    def get_device(self, name: str):
        """Return a plugged-in device by slot name."""
        return self.devices[name]

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
