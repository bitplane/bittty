"""Control operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import constants
from ..operations import Operation

if TYPE_CHECKING:
    from .board import TerminalBoard

logger = logging.getLogger(__name__)


class ControlDevice:
    """Applies C0 and simple control operations to the current Terminal implementation."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.cursor = board.cursor
        self.charset = board.charset

    def handle_operation(self, operation: Operation) -> None:
        ch = operation.raw
        if ch == constants.BEL:
            self.board.bell()
        elif ch == constants.BS:
            self.cursor.backspace()
        elif ch == constants.HT:
            self.cursor.horizontal_tab()
        elif ch in (constants.LF, constants.VT, constants.FF):
            self.cursor.line_feed()
        elif ch == constants.CR:
            self.cursor.carriage_return()
        elif ch == constants.SO:
            self.charset.shift_out()
        elif ch == constants.SI:
            self.charset.shift_in()
        elif ch == constants.DEL:
            pass
        elif operation.name == "IND":
            self.cursor.line_feed()
        elif operation.name == "RI":
            self.cursor.reverse_index()
        elif operation.name == "ST":
            pass
        elif operation.name == "NEL":
            self.cursor.carriage_return()
            self.cursor.line_feed()
        elif operation.name == "HTS":
            self.cursor.set_tab_stop()
        else:
            logger.debug("Unknown control operation: %s", operation)
