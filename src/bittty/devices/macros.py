"""Macro memory: DECDMAC definitions, DECINVM invocation, and their reports."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..operations import Operation
from ..parser import Parser
from .base import Device

if TYPE_CHECKING:
    from .board import Board

# Text-encoded macros hold only graphic characters (VT510: 2/0-7/14 and 10/0-15/15).
_NOT_TEXT = re.compile(r"[^\x20-\x7e\xa0-\xff]")
# Hex-encoded: pairs, and repeat sequences ! Pn ; pairs ;
_HEX_PART = re.compile(r"!([0-9]*);((?:[0-9A-Fa-f]{2})*);|((?:[0-9A-Fa-f]{2})+)")


class MacroDevice(Device):
    """Stores up to the model's macro space of definitions and runs them on request."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.space = board.model.macro_space
        self.macros: dict[int, str] = {}
        self._running: set[int] = set()
        self.handlers = {}
        if self.space is not None:
            self.handlers = {
                "DECDMAC": self.define,
                "DECINVM": self.invoke,
                "DSR_MACRO_SPACE": self.report_space,
                "DSR_MEMORY_CHECKSUM": self.report_checksum,
            }

    def define(self, operation: Operation) -> None:
        """DECDMAC — (re)define a macro; a definition that does not fit is not stored."""
        pid, pdt, pen, body = operation.args
        if not 0 <= pid <= 63 or pdt not in (0, 1) or pen not in (0, 1):
            return
        data = self._decode_hex(body) if pen else _NOT_TEXT.sub("", body)
        if data is None:
            return
        if pdt:
            self.macros.clear()
        self.macros.pop(pid, None)
        if data and len(data) <= self.free:
            self.macros[pid] = data

    def _decode_hex(self, body: str) -> str | None:
        """Hex pairs, with ! Pn ; ... ; repeats (Pn omitted: once); None if malformed or too long."""
        data = []
        position = 0
        for match in _HEX_PART.finditer(body):
            if match.start() != position:
                return None
            count, repeated, plain = match.groups()
            pairs = plain if plain is not None else repeated
            times = 1 if plain is not None else int(count or 1)
            if len(pairs) // 2 * times > self.free:  # bound the expansion before making it
                return None
            data.append(bytes.fromhex(pairs).decode("latin-1") * times)
            position = match.end()
        return "".join(data) if position == len(body) else None

    @property
    def free(self) -> int:
        return self.space - sum(len(data) for data in self.macros.values())

    def invoke(self, operation: Operation) -> None:
        """DECINVM — run a macro as if the host had sent it. A running macro cannot be invoked again."""
        pid = operation.args[0]
        data = self.macros.get(pid)
        if data is None or pid in self._running:
            return
        self._running.add(pid)
        try:
            Parser(self.board).feed(data)
        finally:
            self._running.discard(pid)

    def report_space(self, operation: Operation) -> None:
        """DECMSR — the free macro space in 16-byte units."""
        self.board.host.write(f"\x1b[{self.free // 16:04d}*{{", flush=True)

    def report_checksum(self, operation: Operation) -> None:
        """DECCKSR — a checksum of the stored macros: the 16-bit negated sum of their bytes."""
        total = sum(ord(char) for data in self.macros.values() for char in data)
        self.board.host.write(f"\x1bP{operation.args[0]}!~{-total & 0xFFFF:04X}\x1b\\", flush=True)

    def reset(self, hard: bool = True) -> None:
        """RIS clears every definition; DECSTR keeps them."""
        if hard:
            self.macros.clear()
