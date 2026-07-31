"""Control operation handler for the current board state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Device

if TYPE_CHECKING:
    from .board import Board


class ControlDevice(Device):
    """Applies C0 and simple control operations to the current board implementation."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.cursor = board.cursor
        self.charset = board.charset
        self.handlers = {
            "C0_ENQ": lambda op: self.answerback(),
            "C0_BEL": lambda op: self.board.bell(),
            "C0_BS": lambda op: self.cursor.backspace(),
            "C0_HT": lambda op: self.cursor.horizontal_tab(),
            "C0_LF": lambda op: self.cursor.line_feed(print_trigger="\n"),
            "C0_VT": lambda op: self.cursor.line_feed(print_trigger="\x0b"),
            "C0_FF": lambda op: self.cursor.line_feed(print_trigger="\x0c"),
            "C0_CR": lambda op: self.cursor.carriage_return(),
            "C0_CRLF": lambda op: self.carriage_return_line_feed(),
            "C0_SO": lambda op: self.charset.shift_out(),
            "C0_SI": lambda op: self.charset.shift_in(),
            "C0_DEL": lambda op: None,
            "IND": lambda op: self.cursor.line_feed(),
            "RI": lambda op: self.cursor.reverse_index(),
            "ST": lambda op: None,
            "NEL": lambda op: self.next_line(),
            "HTS": lambda op: self.cursor.set_tab_stop(),
            "S7C1T": lambda op: setattr(self.board, "c1_eightbit", False),
            "S8C1T": lambda op: setattr(self.board, "c1_eightbit", True),
            "ANSI_LEVEL": lambda op: setattr(self.board, "ansi_conformance_level", op.args[0]),
        }

    def carriage_return_line_feed(self) -> None:
        """CR+LF as one fused token (the parser batches the pair)."""
        self.cursor.carriage_return()
        self.cursor.line_feed(print_trigger="\n")

    def next_line(self) -> None:
        """NEL — carriage return followed by line feed."""
        self.cursor.carriage_return()
        self.cursor.line_feed()

    def answerback(self) -> None:
        """ENQ — transmit the programmed answerback string, if any is set."""
        self.board.send_answerback()
