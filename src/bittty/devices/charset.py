"""Charset operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class CharsetDevice:
    """Applies charset and single-shift operations to the current Terminal implementation."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal

    def handle_escape_operation(self, operation: Operation) -> None:
        if operation.name == "SS2":
            self.terminal.single_shift_2()
            return
        if operation.name == "SS3":
            self.terminal.single_shift_3()
            return

        logger.debug("Unknown escape operation: %s", operation)

    def handle_charset_operation(self, operation: Operation) -> None:
        (charset,) = operation.args
        if operation.name == "SCS_G0":
            self.terminal.set_g0_charset(charset)
            return
        if operation.name == "SCS_G1":
            self.terminal.set_g1_charset(charset)
            return
        if operation.name == "SCS_G2":
            self.terminal.set_g2_charset(charset)
            return
        if operation.name == "SCS_G3":
            self.terminal.set_g3_charset(charset)
            return

        logger.debug("Unknown charset operation: %s", operation)
