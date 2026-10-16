"""Images drawn in text, for a terminal (chrome) that shows them on a venue with no graphics.

A set of glyphs splits each cell into a grid of pixels, each drawn in one of two colours: the
glyph's ink (the foreground) or the cell's background. The rasterizer samples the image at
those pixels, picks the two colours for each cell, and finds the glyph inking the right ones.
Coloured spaces need nothing of the venue but colour; half blocks need UTF-8, and are the
only glyphs whose two pixels always get their own colours.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from operator import mul

from ..image import Band, Placement
from ..style import Color, Style
from ..video import CONTINUATION, Cell, WideHead

# A cell drawn: (ink, background, glyph); no background shows the text's behind it. None leaves the text.
Ink = tuple[Color | None, Color | None, str] | None


@dataclass(frozen=True)
class Glyphs:
    """Glyphs splitting a cell into `columns` x `rows` pixels: `chars[mask]` inks the pixels whose
    bits are set in mask, counting row by row from the top left."""

    columns: int
    rows: int
    chars: str


SPACES = Glyphs(1, 1, "  ")
HALF_BLOCKS = Glyphs(1, 2, " ▀▄█")


@lru_cache(maxsize=32)
def rasterize(placement: Placement, glyphs: Glyphs) -> tuple[tuple[Ink, ...], ...]:
    """The cells of each of a placement's rows, drawn in glyphs."""
    image = placement.image
    cell_width, cell_height = placement.cell
    across, down = glyphs.columns, glyphs.rows
    pixels = memoryview(image.rgba)

    def sample(left: int, top: int, right: int, bottom: int) -> tuple[int, int, int] | None:
        """The colour over a box of the image, alpha-weighted; None if mostly clear or past the image."""
        right, bottom = min(right, image.width), min(bottom, image.height)
        area = (right - left) * (bottom - top)
        if area <= 0:
            return None
        r = g = b = a = 0
        for y in range(top, bottom):
            span = pixels[(y * image.width + left) * 4 : (y * image.width + right) * 4]
            alpha = span[3::4]
            a += sum(alpha)
            r += sum(map(mul, span[0::4], alpha))
            g += sum(map(mul, span[1::4], alpha))
            b += sum(map(mul, span[2::4], alpha))
        if 2 * a < 255 * area:
            return None
        return r // a, g // a, b // a

    rows = []
    for row in range(placement.rows):
        cells = []
        for column in range(placement.columns):
            samples = []
            for j in range(down):
                top = row * cell_height + j * cell_height // down
                bottom = max(top + 1, row * cell_height + (j + 1) * cell_height // down)
                for i in range(across):
                    left = column * cell_width + i * cell_width // across
                    right = max(left + 1, column * cell_width + (i + 1) * cell_width // across)
                    samples.append(sample(left, top, right, bottom))
            cells.append(_ink(samples, glyphs.chars))
        rows.append(tuple(cells))
    return tuple(rows)


def _ink(samples: list[tuple[int, int, int] | None], chars: str) -> Ink:
    """Split a cell's pixels into ink and background, and find the glyph for them."""
    shown = [pixel for pixel in samples if pixel is not None]
    if not shown:
        return None
    if len(shown) < len(samples):  # clear pixels show the text's background, the rest are ink
        mask = sum(1 << bit for bit, pixel in enumerate(samples) if pixel is not None)
        return Color("rgb", _mean(shown)), None, chars[mask]
    # Split at the middle of the channel that varies most; the top left pixel's side is the ink.
    spread, channel = max((max(p[c] for p in shown) - min(p[c] for p in shown), c) for c in range(3))
    if not spread:
        return None, Color("rgb", shown[0]), chars[0]
    middle = (max(p[channel] for p in shown) + min(p[channel] for p in shown)) / 2
    side = samples[0][channel] > middle
    mask = sum(1 << bit for bit, pixel in enumerate(samples) if (pixel[channel] > middle) == side)
    ink = [pixel for pixel in samples if (pixel[channel] > middle) == side]
    paper = [pixel for pixel in samples if (pixel[channel] > middle) != side]
    return Color("rgb", _mean(ink)), Color("rgb", _mean(paper)), chars[mask]


def _mean(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    return tuple(sum(channel) // len(pixels) for channel in zip(*pixels))


def composite(cells: Sequence[Cell], bands: Sequence[Band], glyphs: Glyphs) -> list[Cell]:
    """A row of text with the images on it drawn over, in order, cut at the row's end."""
    row = list(cells)
    for band in bands:
        start = band.placement.column
        for x, ink in enumerate(rasterize(band.placement, glyphs)[band.row][: len(row) - start], start):
            if ink is None:
                continue
            behind, char = row[x]
            # Half a wide glyph cannot show: blank the other half.
            if char == CONTINUATION:
                row[x - 1] = (row[x - 1][0], " ")
            elif isinstance(char, WideHead) and x + 1 < len(row):
                row[x + 1] = (row[x + 1][0], " ")
            fg, bg, glyph = ink
            row[x] = (Style(fg=fg, bg=behind.bg if bg is None else bg), glyph)
    return row
