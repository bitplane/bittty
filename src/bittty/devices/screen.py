"""Screen and editing operation handlers for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import constants
from ..operations import Operation

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class ScreenDevice:
    """Applies screen and editing operations to the current Terminal implementation."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal

    def handle_edit_operation(self, operation: Operation) -> None:
        if operation.name == "ED":
            (mode,) = operation.args
            self.terminal.clear_screen(mode)
            return
        if operation.name == "EL":
            (mode,) = operation.args
            self.terminal.clear_line(mode)
            return
        if operation.name == "IL":
            (count,) = operation.args
            self.terminal.insert_lines(count)
            return
        if operation.name == "DL":
            (count,) = operation.args
            self.terminal.delete_lines(count)
            return
        if operation.name == "ICH":
            (count,) = operation.args
            self.terminal.insert_characters(count, self.terminal.current_ansi_code)
            return
        if operation.name == "DCH":
            (count,) = operation.args
            self.terminal.delete_characters(count)
            return
        if operation.name == "ECH":
            (count,) = operation.args
            for _ in range(count):
                self.terminal.current_buffer.set(
                    self.terminal.cursor_x,
                    self.terminal.cursor_y,
                    " ",
                    self.terminal.current_ansi_code,
                )
                if self.terminal.cursor_x < self.terminal.width - 1:
                    self.terminal.cursor_x += 1
            return
        if operation.name == "SU":
            (count,) = operation.args
            self.terminal.scroll(count)
            return
        if operation.name == "SD":
            (count,) = operation.args
            self.terminal.scroll(-count)
            return
        if operation.name == "REP":
            (count,) = operation.args
            self.terminal.repeat_last_character(count)
            return

        logger.debug("Unknown edit operation: %s", operation)

    def handle_screen_operation(self, operation: Operation) -> None:
        if operation.name == "DECSTBM":
            top, bottom = operation.args
            self.terminal.set_scroll_region(top, self.terminal.height - 1 if bottom is None else bottom)
            return
        if operation.name == "RIS":
            self.terminal.clear_screen(constants.ERASE_ALL)
            self.terminal.set_cursor(0, 0)
            self.terminal.current_ansi_code = ""
            self.terminal.set_g0_charset("B")
            self.terminal.set_g1_charset("B")
            self.terminal.set_g2_charset("B")
            self.terminal.set_g3_charset("B")
            self.terminal.current_charset = 0
            self.terminal.single_shift = None
            return

        logger.debug("Unknown screen operation: %s", operation)
