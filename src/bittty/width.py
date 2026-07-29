"""Terminal column-width policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from wcwidth import wcwidth


@dataclass(frozen=True, slots=True)
class WidthPolicy:
    """How printable Unicode code points occupy terminal columns."""

    ambiguous_width: Literal[1, 2] = 1

    def __post_init__(self) -> None:
        if self.ambiguous_width not in (1, 2):
            raise ValueError("ambiguous_width must be 1 or 2")

    def width(self, char: str) -> int:
        """Return one or two columns for one code point.

        Zero-width and multi-code-point grapheme behaviour is deliberately
        deferred; those code points retain the emulator's legacy one-cell
        behaviour in this milestone.
        """
        if len(char) != 1:
            raise ValueError("width() requires exactly one code point")
        if char.isascii():
            return 1
        return 2 if wcwidth(char, ambiguous_width=self.ambiguous_width) == 2 else 1


DEFAULT_WIDTH_POLICY = WidthPolicy()
