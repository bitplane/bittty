"""Query operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation
from .modes import ModeDevice

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class QueryDevice:
    """Applies terminal query operations to the current Terminal implementation."""

    def __init__(self, terminal: Terminal, modes: ModeDevice) -> None:
        self.terminal = terminal
        self.modes = modes

    def handle_operation(self, operation: Operation) -> None:
        if operation.name == "CPR":
            row = self.terminal.cursor_y + 1
            col = self.terminal.cursor_x + 1
            self.terminal.respond(f"\033[{row};{col}R")
            return
        if operation.name == "DSR":
            self.terminal.respond("\033[0n")
            return
        if operation.name == "DA1":
            self.terminal.respond("\033[?62;1;6;8;9;15;18;21;22;23c")
            return
        if operation.name == "DA2":
            self.terminal.respond("\033[>1;10;0c")
            return
        if operation.name == "DECRQM":
            mode, private = operation.args
            if private:
                status = self.modes.get_private_mode_status(mode)
            else:
                status = self.modes.get_ansi_mode_status(mode)
            prefix = "?" if private else ""
            self.terminal.respond(f"\033[{prefix}{mode};{status}$y")
            return
        if operation.name == "OSC_FOREGROUND_COLOR":
            self.terminal.respond("\033]10;rgb:ffff/ffff/ffff\007")
            return
        if operation.name == "OSC_BACKGROUND_COLOR":
            self.terminal.respond("\033]11;rgb:0000/0000/0000\007")
            return

        logger.debug("Unknown query operation: %s", operation)
