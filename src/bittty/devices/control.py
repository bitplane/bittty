"""Control operation handler for the current Terminal state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Device

if TYPE_CHECKING:
    from .board import TerminalBoard


class ControlDevice(Device):
    """Applies C0 and simple control operations to the current Terminal implementation."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.cursor = board.cursor
        self.charset = board.charset
        self.handlers = {
            "C0_ENQ": lambda op: self.answerback(),
            "C0_BEL": lambda op: self.board.bell(),
            "C0_BS": lambda op: self.cursor.backspace(),
            "C0_HT": lambda op: self.cursor.horizontal_tab(),
            "C0_LF": lambda op: self.cursor.line_feed(),
            "C0_VT": lambda op: self.cursor.line_feed(),
            "C0_FF": lambda op: self.cursor.line_feed(),
            "C0_CR": lambda op: self.cursor.carriage_return(),
            "C0_SO": lambda op: self.charset.shift_out(),
            "C0_SI": lambda op: self.charset.shift_in(),
            "C0_DEL": lambda op: None,
            "IND": lambda op: self.cursor.line_feed(),
            "RI": lambda op: self.cursor.reverse_index(),
            "ST": lambda op: None,
            "NEL": lambda op: self.next_line(),
            "HTS": lambda op: self.cursor.set_tab_stop(),
        }

    def next_line(self) -> None:
        """NEL — carriage return followed by line feed."""
        self.cursor.carriage_return()
        self.cursor.line_feed()

    def answerback(self) -> None:
        """ENQ — transmit the programmed answerback string, if any is set."""
        if self.board.answerback:
            self.board.host.write(self.board.answerback, flush=True)
