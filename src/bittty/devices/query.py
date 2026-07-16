"""Query operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation

if TYPE_CHECKING:
    from .board import TerminalBoard

logger = logging.getLogger(__name__)


class QueryDevice:
    """Applies terminal query operations to the current Terminal implementation."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.modes = board.modes

    def handle_operation(self, operation: Operation) -> None:
        if operation.name == "CPR":
            row = self.board.cursor.y + 1
            col = self.board.cursor.x + 1
            self.board.host.write(f"\033[{row};{col}R", flush=True)
            return
        if operation.name == "DSR":
            self.board.host.write("\033[0n", flush=True)
            return
        if operation.name == "DA1":
            self.board.host.write("\033[?62;1;6;8;9;15;18;21;22;23c", flush=True)
            return
        if operation.name == "DA2":
            self.board.host.write("\033[>1;10;0c", flush=True)
            return
        if operation.name == "DECRQM":
            mode, private = operation.args
            if private:
                status = self.modes.get_private_mode_status(mode)
            else:
                status = self.modes.get_ansi_mode_status(mode)
            prefix = "?" if private else ""
            self.board.host.write(f"\033[{prefix}{mode};{status}$y", flush=True)
            return
        if operation.name == "OSC_FOREGROUND_COLOR":
            self.board.host.write("\033]10;rgb:ffff/ffff/ffff\007", flush=True)
            return
        if operation.name == "OSC_BACKGROUND_COLOR":
            self.board.host.write("\033]11;rgb:0000/0000/0000\007", flush=True)
            return

        logger.debug("Unknown query operation: %s", operation)
