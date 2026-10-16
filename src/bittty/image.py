"""Images in video memory: pixels, where they are placed, and the bands that carry them on rows.

Every graphics protocol decodes into these, and every terminal (chrome) draws from them, so
neither end knows the other's protocol. An image is placed against an anchor cell; each row it
covers holds a band naming the placement and which of its cell rows that is, so the image moves
with its rows as they scroll, into history and out of it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, eq=False)
class Image:
    """Pixels: `width` x `height`, row-major RGBA, eight bits a channel."""

    width: int
    height: int
    rgba: bytes


@dataclass(frozen=True, slots=True, eq=False)
class Placement:
    """An image placed with its top left at the top left of a cell in `column`, laid out on
    cells `cell` pixels (width, height) in size: the cells it reaches are the ones it covers."""

    image: Image
    column: int
    cell: tuple[int, int]

    @property
    def columns(self) -> int:
        return -(-self.image.width // self.cell[0])

    @property
    def rows(self) -> int:
        return -(-self.image.height // self.cell[1])


@dataclass(frozen=True, slots=True)
class Band:
    """The part of a placement on one row: its cell row `row`, counting from 0 at the top."""

    placement: Placement
    row: int
