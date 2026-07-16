"""Colour palettes: the index -> RGB mapping a terminal presents.

bittty stores colours symbolically (a `Style` holds an indexed or rgb `Color`);
the palette is the authoritative map an indexed colour resolves *through*. It is
seeded from the personality, mutated by OSC colour sequences, and queried by
their `?` forms. Rendering to real pixels stays a frontend concern — the
frontend calls `PaletteDevice.resolve()` when it wants RGB.
"""

from __future__ import annotations

from dataclasses import dataclass

RGB = tuple[int, int, int]

# xterm's canonical default 16 ANSI colours (0-7 normal, 8-15 bright).
XTERM_16: tuple[RGB, ...] = (
    (0, 0, 0),
    (205, 0, 0),
    (0, 205, 0),
    (205, 205, 0),
    (0, 0, 238),
    (205, 0, 205),
    (0, 205, 205),
    (229, 229, 229),
    (127, 127, 127),
    (255, 0, 0),
    (0, 255, 0),
    (255, 255, 0),
    (92, 92, 255),
    (255, 0, 255),
    (0, 255, 255),
    (255, 255, 255),
)

# The linux console's default palette (VGA-derived), distinct from xterm's.
VGA_16: tuple[RGB, ...] = (
    (0, 0, 0),
    (170, 0, 0),
    (0, 170, 0),
    (170, 85, 0),
    (0, 0, 170),
    (170, 0, 170),
    (0, 170, 170),
    (170, 170, 170),
    (85, 85, 85),
    (255, 85, 85),
    (85, 255, 85),
    (255, 255, 85),
    (85, 85, 255),
    (255, 85, 255),
    (85, 255, 255),
    (255, 255, 255),
)

_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)


def build_256(base16: tuple[RGB, ...]) -> list[RGB]:
    """Build the full 256-colour table: 16 base + 216 colour cube + 24 greys."""
    colors: list[RGB] = list(base16)
    for r in _CUBE_LEVELS:
        for g in _CUBE_LEVELS:
            for b in _CUBE_LEVELS:
                colors.append((r, g, b))
    for i in range(24):
        v = 8 + i * 10
        colors.append((v, v, v))
    return colors


def _scale(hexstr: str) -> int | None:
    """Scale a 1-4 digit hex channel to 8 bits (X11 semantics)."""
    n = len(hexstr)
    if n == 0 or n > 4:
        return None
    try:
        value = int(hexstr, 16)
    except ValueError:
        return None
    return round(value * 255 / ((1 << (4 * n)) - 1))


def parse_color_spec(spec: str) -> RGB | None:
    """Parse an X11 colour spec: ``rgb:R/G/B`` or ``#RGB``/``#RRGGBB``/... ."""
    spec = spec.strip()
    if spec.startswith("rgb:"):
        parts = spec[4:].split("/")
    elif spec.startswith("#"):
        body = spec[1:]
        if len(body) == 0 or len(body) % 3 != 0:
            return None
        n = len(body) // 3
        parts = [body[0:n], body[n : 2 * n], body[2 * n : 3 * n]]
    else:
        return None

    if len(parts) != 3:
        return None
    channels = [_scale(p) for p in parts]
    if any(c is None for c in channels):
        return None
    return (channels[0], channels[1], channels[2])


def format_rgb(rgb: RGB) -> str:
    """Format an RGB triple as an X11 ``rgb:rrrr/gggg/bbbb`` reply string."""
    return "rgb:" + "/".join(f"{(c << 8) | c:04x}" for c in rgb)


@dataclass(frozen=True)
class PaletteDefaults:
    """A terminal's default colours: the 16 ANSI colours plus fg/bg/cursor."""

    base16: tuple[RGB, ...] = XTERM_16
    foreground: RGB = (255, 255, 255)
    background: RGB = (0, 0, 0)
    cursor: RGB = (255, 255, 255)


XTERM_PALETTE = PaletteDefaults()

VGA_PALETTE = PaletteDefaults(
    base16=VGA_16,
    foreground=(170, 170, 170),
    background=(0, 0, 0),
    cursor=(170, 170, 170),
)
