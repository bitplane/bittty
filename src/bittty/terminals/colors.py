"""Colour reduction: a style's colours brought within what a venue can show.

The board keeps whatever colours the child asked for. A terminal (chrome) on a venue of fewer
colours paints the nearest it has: an RGB colour becomes the nearest of the 256-colour cube and
greys (never 0-15, whose colours are the venue's own to choose), or of the 16 ANSI colours as
xterm draws them by default; monochrome drops colour and keeps every other attribute.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from ..palette import RGB, XTERM_16, build_256
from ..style import Color, Style
from ..video import Cell

# The depths a venue may have that are short of truecolor.
REDUCED = frozenset({"256", "16", "monochrome"})
_TABLE = build_256(XTERM_16)


def _nearest(rgb: RGB, indexes: range) -> int:
    r, g, b = rgb
    return min(indexes, key=lambda i: (_TABLE[i][0] - r) ** 2 + (_TABLE[i][1] - g) ** 2 + (_TABLE[i][2] - b) ** 2)


@lru_cache(maxsize=4096)
def _color(color: Color | None, depth: str) -> Color | None:
    """A colour brought within 256 or 16 colours."""
    if color is None or color.mode == "default":
        return color
    if depth == "256":
        return color if color.mode == "indexed" else Color("indexed", _nearest(color.value, range(16, 256)))
    if color.mode == "indexed" and color.value < 16:
        return color
    rgb = _TABLE[color.value] if color.mode == "indexed" else color.value
    return Color("indexed", _nearest(rgb, range(16)))


@lru_cache(maxsize=4096)
def reduce_style(style: Style, depth: str) -> Style:
    """A style with its colours brought within a depth in REDUCED."""
    if depth == "monochrome":
        return style.replace(fg=None, bg=None, underline_color=None)
    underline = None if depth == "16" else _color(style.underline_color, depth)  # SGR 58 has no 16-colour form
    return style.replace(fg=_color(style.fg, depth), bg=_color(style.bg, depth), underline_color=underline)


def reduce_cells(cells: Sequence[Cell], depth: str) -> list[Cell]:
    """A row of cells in colours a depth in REDUCED has."""
    return [(reduce_style(style, depth), char) for style, char in cells]
