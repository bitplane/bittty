from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Literal, Tuple, Union, Optional


# --- Color Model --- #


@dataclass(frozen=True)
class Color:
    mode: Literal["default", "indexed", "rgb"]
    value: Union[int, Tuple[int, int, int], None] = None

    @property
    @lru_cache
    def ansi(self) -> str:
        if self.mode == "default":
            return ""
        elif self.mode == "indexed":
            return f"5;{self.value}"
        elif self.mode == "rgb":
            r, g, b = self.value
            return f"2;{r};{g};{b}"
        return ""

    def __str__(self) -> str:
        return self.ansi

    def __hash__(self) -> int:
        return hash((self.mode, self.value))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Color):
            return NotImplemented
        return (self.mode, self.value) == (other.mode, other.value)


# --- Style Model --- #


@dataclass(frozen=True)
class Style:
    fg: Color = Color("default")
    bg: Color = Color("default")
    bold: Optional[bool] = None
    dim: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    blink: Optional[bool] = None
    reverse: Optional[bool] = None
    conceal: Optional[bool] = None
    strike: Optional[bool] = None

    def merge(self, other: Style) -> Style:
        """Merge another style into this one. The other style takes precedence."""

        def merge_attr(base_attr, other_attr):
            # If other explicitly sets the attribute (True or False), use it
            if other_attr is not None:
                return other_attr
            # Otherwise keep the base attribute
            return base_attr

        return Style(
            fg=other.fg if other.fg.mode != "default" else self.fg,
            bg=other.bg if other.bg.mode != "default" else self.bg,
            bold=merge_attr(self.bold, other.bold),
            dim=merge_attr(self.dim, other.dim),
            italic=merge_attr(self.italic, other.italic),
            underline=merge_attr(self.underline, other.underline),
            blink=merge_attr(self.blink, other.blink),
            reverse=merge_attr(self.reverse, other.reverse),
            conceal=merge_attr(self.conceal, other.conceal),
            strike=merge_attr(self.strike, other.strike),
        )

    @lru_cache(maxsize=10000)
    def diff(self, other: "Style") -> str:
        """Generate minimal ANSI sequence to transition to another style."""
        if self == other:
            return ""

        if other == Style():  # Target is default
            return "\x1b[0m"

        if self == Style():  # Coming from default
            return style_to_ansi(other)

        # For now, reset + target (can optimize later for partial changes)
        target_ansi = style_to_ansi(other)
        return f"\x1b[0m{target_ansi}" if target_ansi else "\x1b[0m"


# --- ANSI Sequence Parser --- #


@lru_cache(maxsize=10000)
def parse_sgr_sequence(ansi: str) -> Style:
    if not ansi.startswith("\x1b[") or not ansi.endswith("m"):
        return Style()

    tokens = tuple(ansi[2:-1].split(";"))
    return interpret(tokens)


@lru_cache(maxsize=10000)
def interpret(tokens: Tuple[str, ...]) -> Style:
    style = Style()
    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Reset
        if token == "0" or token == "00":
            style = Style()

        # Simple attributes
        elif token == "1" or token == "01":
            style = replace(style, bold=True)
        elif token == "2":
            style = replace(style, dim=True)
        elif token == "3":
            style = replace(style, italic=True)
        elif token == "4":
            style = replace(style, underline=True)
        elif token == "5":
            style = replace(style, blink=True)
        elif token == "7":
            style = replace(style, reverse=True)
        elif token == "8":
            style = replace(style, conceal=True)
        elif token == "9":
            style = replace(style, strike=True)

        elif token == "22":
            style = replace(style, bold=False, dim=False)
        elif token == "23":
            style = replace(style, italic=False)
        elif token == "24":
            style = replace(style, underline=False)
        elif token == "25":
            style = replace(style, blink=False)
        elif token == "27":
            style = replace(style, reverse=False)
        elif token == "28":
            style = replace(style, conceal=False)
        elif token == "29":
            style = replace(style, strike=False)

        # Basic indexed colors
        elif token.isdigit() and 30 <= int(token) <= 37:
            style = replace(style, fg=Color("indexed", int(token) - 30))
        elif token == "39":
            style = replace(style, fg=Color("default"))

        elif token.isdigit() and 40 <= int(token) <= 47:
            style = replace(style, bg=Color("indexed", int(token) - 40))
        elif token == "49":
            style = replace(style, bg=Color("default"))

        # Bright colors
        elif token.isdigit() and 90 <= int(token) <= 97:
            style = replace(style, fg=Color("indexed", int(token) - 90 + 8))
        elif token.isdigit() and 100 <= int(token) <= 107:
            style = replace(style, bg=Color("indexed", int(token) - 100 + 8))

        # Extended color (indexed or rgb)
        elif token in {"38", "48"}:
            is_fg = token == "38"
            if i + 1 < len(tokens):
                mode = tokens[i + 1]
                if mode == "5" and i + 2 < len(tokens):
                    val = int(tokens[i + 2])
                    if is_fg:
                        style = replace(style, fg=Color("indexed", val))
                    else:
                        style = replace(style, bg=Color("indexed", val))
                    i += 2
                elif mode == "2" and i + 4 < len(tokens):
                    r = int(tokens[i + 2])
                    g = int(tokens[i + 3])
                    b = int(tokens[i + 4])
                    if is_fg:
                        style = replace(style, fg=Color("rgb", (r, g, b)))
                    else:
                        style = replace(style, bg=Color("rgb", (r, g, b)))
                    i += 4
        i += 1

    return style


# --- Compatibility Functions --- #


@lru_cache(maxsize=10000)
def get_background(ansi: str) -> str:
    """Extract just the background color as an ANSI sequence.

    Args:
        ansi: ANSI escape sequence

    Returns:
        ANSI sequence with just the background color, or empty string
    """
    style = parse_sgr_sequence(ansi)
    if style.bg.mode == "default":
        return ""
    elif style.bg.mode == "indexed":
        if style.bg.value < 8:
            return f"\x1b[{40 + style.bg.value}m"
        elif style.bg.value < 16:
            return f"\x1b[{100 + style.bg.value - 8}m"
        else:
            return f"\x1b[48;5;{style.bg.value}m"
    elif style.bg.mode == "rgb":
        r, g, b = style.bg.value
        return f"\x1b[48;2;{r};{g};{b}m"
    return ""


@lru_cache(maxsize=10000)
def merge_ansi_styles(base: str, new: str) -> str:
    """Merge two ANSI style sequences, returning a new ANSI sequence.

    Args:
        base: Base ANSI sequence
        new: New ANSI sequence to merge

    Returns:
        Merged ANSI sequence
    """
    # Check for reset sequence first
    if new and ("\x1b[0m" in new or "\x1b[00m" in new):
        # Reset overwrites everything
        return style_to_ansi(parse_sgr_sequence(new))

    # Parse both sequences to Style objects
    base_style = parse_sgr_sequence(base) if base else Style()
    new_style = parse_sgr_sequence(new) if new else Style()

    # Merge the styles
    merged = base_style.merge(new_style)

    # Convert back to ANSI
    return style_to_ansi(merged)


@lru_cache(maxsize=10000)
def style_to_ansi(style: Style) -> str:
    """Convert a Style object back to an ANSI escape sequence.

    Args:
        style: Style object to convert

    Returns:
        ANSI escape sequence string
    """
    if style == Style():  # Default style
        return ""

    params = []

    # Attributes
    if style.bold is True:
        params.append("1")
    if style.dim is True:
        params.append("2")
    if style.italic is True:
        params.append("3")
    if style.underline is True:
        params.append("4")
    if style.blink is True:
        params.append("5")
    if style.reverse is True:
        params.append("7")
    if style.conceal is True:
        params.append("8")
    if style.strike is True:
        params.append("9")

    # Foreground color
    if style.fg.mode == "indexed":
        if style.fg.value < 8:
            params.append(str(30 + style.fg.value))
        elif style.fg.value < 16:
            params.append(str(90 + style.fg.value - 8))
        else:
            params.append(f"38;5;{style.fg.value}")
    elif style.fg.mode == "rgb":
        r, g, b = style.fg.value
        params.append(f"38;2;{r};{g};{b}")

    # Background color
    if style.bg.mode == "indexed":
        if style.bg.value < 8:
            params.append(str(40 + style.bg.value))
        elif style.bg.value < 16:
            params.append(str(100 + style.bg.value - 8))
        else:
            params.append(f"48;5;{style.bg.value}")
    elif style.bg.mode == "rgb":
        r, g, b = style.bg.value
        params.append(f"48;2;{r};{g};{b}")

    if not params:
        return ""

    return f"\x1b[{';'.join(params)}m"


# For backwards compatibility with tests
def _parse_ansi_to_tuple(ansi: str) -> tuple:
    """Legacy function for tests - converts ANSI to tuple representation."""
    style = parse_sgr_sequence(ansi)

    # Convert colors to old format
    fg = None
    if style.fg.mode == "indexed":
        if style.fg.value < 8:
            fg = str(30 + style.fg.value)
        elif style.fg.value < 16:
            fg = str(90 + style.fg.value - 8)
        else:
            fg = f"38;5;{style.fg.value}"
    elif style.fg.mode == "rgb":
        r, g, b = style.fg.value
        fg = f"38;2;{r};{g};{b}"

    bg = None
    if style.bg.mode == "indexed":
        if style.bg.value < 8:
            bg = str(40 + style.bg.value)
        elif style.bg.value < 16:
            bg = str(100 + style.bg.value - 8)
        else:
            bg = f"48;5;{style.bg.value}"
    elif style.bg.mode == "rgb":
        r, g, b = style.bg.value
        bg = f"48;2;{r};{g};{b}"

    return (
        fg,
        bg,
        style.bold,
        style.dim,
        style.italic,
        style.underline,
        style.blink,
        style.reverse,
        style.conceal,
        style.strike,
    )


def _tuple_to_ansi(style_tuple: tuple) -> str:
    """Legacy function for tests - converts tuple to ANSI."""
    fg, bg, bold, dim, italic, underline, blink, reverse, conceal, strike = style_tuple

    # Build a Style object
    style = Style()

    # Parse fg color
    if fg:
        if fg.startswith("38;5;"):
            style = replace(style, fg=Color("indexed", int(fg.split(";")[2])))
        elif fg.startswith("38;2;"):
            parts = fg.split(";")
            style = replace(style, fg=Color("rgb", (int(parts[2]), int(parts[3]), int(parts[4]))))
        elif fg.isdigit():
            val = int(fg)
            if 30 <= val <= 37:
                style = replace(style, fg=Color("indexed", val - 30))
            elif 90 <= val <= 97:
                style = replace(style, fg=Color("indexed", val - 90 + 8))

    # Parse bg color
    if bg:
        if bg.startswith("48;5;"):
            style = replace(style, bg=Color("indexed", int(bg.split(";")[2])))
        elif bg.startswith("48;2;"):
            parts = bg.split(";")
            style = replace(style, bg=Color("rgb", (int(parts[2]), int(parts[3]), int(parts[4]))))
        elif bg.isdigit():
            val = int(bg)
            if 40 <= val <= 47:
                style = replace(style, bg=Color("indexed", val - 40))
            elif 100 <= val <= 107:
                style = replace(style, bg=Color("indexed", val - 100 + 8))

    # Set attributes
    style = replace(style, bold=bold)
    style = replace(style, dim=dim)
    style = replace(style, italic=italic)
    style = replace(style, underline=underline)
    style = replace(style, blink=blink)
    style = replace(style, reverse=reverse)
    style = replace(style, conceal=conceal)
    style = replace(style, strike=strike)

    return style_to_ansi(style)
