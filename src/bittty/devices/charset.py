"""Charset operation handler for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..charsets import get_charset
from ..operations import Operation

if TYPE_CHECKING:
    from .board import TerminalBoard

logger = logging.getLogger(__name__)


class CharsetDevice:
    """Owns charset state and applies charset operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.g0_charset = "B"
        self.g1_charset = "B"
        self.g2_charset = "B"
        self.g3_charset = "B"
        self.current_charset = 0
        self.single_shift: int | None = None
        self.cache = {}
        self.charset_array = ["B", "B", "B", "B"]

    def translate(self, text: str) -> str:
        """Translate text through the active character set."""
        if self.single_shift is not None:
            if not text:
                return text

            first_char = text[0]
            remaining = text[1:] if len(text) > 1 else ""
            charset_designator = self.charset_array[self.single_shift]
            self.single_shift = None

            charset_map = self._get_charset_map(charset_designator)
            translated_first = charset_map.get(first_char, first_char)

            if remaining:
                return translated_first + self.translate(remaining)
            return translated_first

        current_charset_designator = self.charset_array[self.current_charset]
        if current_charset_designator == "B" or not text:
            return text

        charset_map = self._get_charset_map(current_charset_designator)
        if not charset_map:
            return text

        return "".join(charset_map.get(char, char) for char in text)

    def _get_charset_map(self, charset_designator: str):
        if charset_designator not in self.cache:
            self.cache[charset_designator] = get_charset(charset_designator)
        return self.cache[charset_designator]

    def set_g0_charset(self, charset: str) -> None:
        """Set the G0 character set."""
        self.g0_charset = charset
        self.charset_array[0] = charset

    def set_g1_charset(self, charset: str) -> None:
        """Set the G1 character set."""
        self.g1_charset = charset
        self.charset_array[1] = charset

    def set_g2_charset(self, charset: str) -> None:
        """Set the G2 character set."""
        self.g2_charset = charset
        self.charset_array[2] = charset

    def set_g3_charset(self, charset: str) -> None:
        """Set the G3 character set."""
        self.g3_charset = charset
        self.charset_array[3] = charset

    def shift_in(self) -> None:
        """Shift In (SI) - switch to G0."""
        self.current_charset = 0

    def shift_out(self) -> None:
        """Shift Out (SO) - switch to G1."""
        self.current_charset = 1

    def single_shift_2(self) -> None:
        """Single Shift 2 (SS2) - use G2 for next character only."""
        self.single_shift = 2

    def single_shift_3(self) -> None:
        """Single Shift 3 (SS3) - use G3 for next character only."""
        self.single_shift = 3

    def reset(self) -> None:
        """Reset charset selections to US ASCII."""
        self.set_g0_charset("B")
        self.set_g1_charset("B")
        self.set_g2_charset("B")
        self.set_g3_charset("B")
        self.current_charset = 0
        self.single_shift = None

    def handle_escape_operation(self, operation: Operation) -> None:
        if operation.name == "SS2":
            self.single_shift_2()
            return
        if operation.name == "SS3":
            self.single_shift_3()
            return

        logger.debug("Unknown escape operation: %s", operation)

    def handle_charset_operation(self, operation: Operation) -> None:
        (charset,) = operation.args
        if operation.name == "SCS_G0":
            self.set_g0_charset(charset)
            return
        if operation.name == "SCS_G1":
            self.set_g1_charset(charset)
            return
        if operation.name == "SCS_G2":
            self.set_g2_charset(charset)
            return
        if operation.name == "SCS_G3":
            self.set_g3_charset(charset)
            return

        logger.debug("Unknown charset operation: %s", operation)
