"""Control operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import constants
from ..operations import Operation

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class ControlDevice:
    """Applies C0 and simple control operations to the current Terminal implementation."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal

    def handle_operation(self, operation: Operation) -> None:
        ch = operation.raw
        if ch == constants.BEL:
            self.terminal.bell()
        elif ch == constants.BS:
            self.terminal.backspace()
        elif ch == constants.HT:
            self.terminal.cursor_x = self.terminal.next_tab_stop()
        elif ch in (constants.LF, constants.VT, constants.FF):
            self.terminal.line_feed()
        elif ch == constants.CR:
            self.terminal.cursor_x = 0
        elif ch == constants.SO:
            self.terminal.current_charset = 1
        elif ch == constants.SI:
            self.terminal.current_charset = 0
        elif ch == constants.DEL:
            pass
        elif operation.name == "IND":
            self.terminal.line_feed()
        elif operation.name == "RI":
            if self.terminal.cursor_y <= self.terminal.scroll_top:
                self.terminal.scroll(-1)
            else:
                self.terminal.cursor_y -= 1
        elif operation.name == "ST":
            pass
        elif operation.name == "NEL":
            self.terminal.cursor_x = 0
            self.terminal.line_feed()
        elif operation.name == "HTS":
            self.terminal.set_tab_stop(self.terminal.cursor_x)
        else:
            logger.debug("Unknown control operation: %s", operation)
