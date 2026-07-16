from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Literal, Tuple, Union, Optional


# --- Constants --- #

CURSOR_CODE = "\033[7m"  # Reverse video for cursor display
RESET_CODE = "\033[0m"  # Reset all formatting


# --- Color Model --- #


@dataclass(frozen=True, slots=True)
class Color:
    mode: Literal["default", "indexed", "rgb"]
    value: Union[int, Tuple[int, int, int], None] = None

    @property
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


@dataclass(frozen=True, slots=True)
class Style:
    fg: Optional[Color] = None
    bg: Optional[Color] = None
    bold: Optional[bool] = None
    dim: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    blink: Optional[bool] = None
    reverse: Optional[bool] = None
    conceal: Optional[bool] = None
    strike: Optional[bool] = None
    underline_style: Optional[str] = None  # None=single / "double" / "curly" / "dotted" / "dashed"
    overline: Optional[bool] = None
    underline_color: Optional[Color] = None
    font: Optional[int] = None  # SGR 10-19: 0 = primary, 1-9 = alternate fonts
    fraktur: Optional[bool] = None  # SGR 20 (blackletter)
    framed: Optional[bool] = None  # SGR 51
    encircled: Optional[bool] = None  # SGR 52
    ideogram: Optional[str] = None  # SGR 60-65: underline/double_underline/overline/double_overline/stress/none
    hyperlink: Optional[str] = None  # OSC 8 target URI (not an SGR attribute)
    protected: Optional[bool] = None  # DECSCA: shielded from selective erase

    def merge(self, other: Style) -> Style:
        """Merge another style into this one; the other's non-None attributes win.

        The per-field ``x if x is not None else y`` is inlined (no helper closure):
        this is the hottest path in the emulator — one call per printed cell that
        changes style — so the ~17 closure calls per merge are worth removing.
        """
        return Style(
            fg=other.fg if other.fg is not None else self.fg,
            bg=other.bg if other.bg is not None else self.bg,
            bold=other.bold if other.bold is not None else self.bold,
            dim=other.dim if other.dim is not None else self.dim,
            italic=other.italic if other.italic is not None else self.italic,
            underline=other.underline if other.underline is not None else self.underline,
            blink=other.blink if other.blink is not None else self.blink,
            reverse=other.reverse if other.reverse is not None else self.reverse,
            conceal=other.conceal if other.conceal is not None else self.conceal,
            strike=other.strike if other.strike is not None else self.strike,
            underline_style=other.underline_style if other.underline_style is not None else self.underline_style,
            overline=other.overline if other.overline is not None else self.overline,
            underline_color=other.underline_color if other.underline_color is not None else self.underline_color,
            font=other.font if other.font is not None else self.font,
            fraktur=other.fraktur if other.fraktur is not None else self.fraktur,
            framed=other.framed if other.framed is not None else self.framed,
            encircled=other.encircled if other.encircled is not None else self.encircled,
            ideogram=other.ideogram if other.ideogram is not None else self.ideogram,
            hyperlink=other.hyperlink if other.hyperlink is not None else self.hyperlink,
            protected=other.protected if other.protected is not None else self.protected,
        )

    def diff(self, other: "Style") -> str:
        """Generate minimal ANSI sequence to transition to another style."""
        return _style_diff(self, other)


@lru_cache(maxsize=10000)
def _style_diff(a: "Style", b: "Style") -> str:
    """Cached style transition (module-level so Style can use __slots__)."""
    if a == b:
        return ""
    if b == Style():  # Target is default
        return "\x1b[0m"
    if a == Style():  # Coming from default
        return style_to_ansi(b)
    # For now, reset + target (can optimize later for partial changes)
    target_ansi = style_to_ansi(b)
    return f"\x1b[0m{target_ansi}" if target_ansi else "\x1b[0m"


# --- ANSI Sequence Parser --- #


@lru_cache(maxsize=10000)
def parse_sgr_sequence(ansi: str) -> Style:
    if not ansi.startswith("\x1b[") or not ansi.endswith("m"):
        return Style()

    tokens = tuple(ansi[2:-1].split(";"))
    return interpret(tokens)


_RESET_TOKENS = ("", "0", "00")


def _last_reset_index(tokens: Tuple[str, ...]) -> int:
    """Index of the last SGR reset token, skipping 38/48/58 colour arguments.

    A bare "0" can also be a colour channel (38;2;0;0;0), so the walk consumes
    extended-colour arguments exactly like interpret() does.
    """
    last = -1
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in _RESET_TOKENS:
            last = i
        elif token in ("38", "48", "58") and i + 1 < len(tokens):
            i += 2 if tokens[i + 1] == "5" else 4 if tokens[i + 1] == "2" else 0
        i += 1
    return last


@lru_cache(maxsize=10000)
def parse_sgr_with_reset(ansi: str) -> Tuple[Optional[Style], bool]:
    """Parse an SGR sequence into (style, reset): reset means "clear, then apply style".

    A reset token (0, 00, or an empty parameter) anywhere in the sequence discards
    everything before it, so ESC[0;31m is "reset, then red" — not a red merge into
    the current attributes. A pure reset returns (None, True) so the hot path can
    skip the merge without comparing 20 Style fields.
    """
    if not ansi.startswith("\x1b[") or not ansi.endswith("m"):
        return Style(), False
    tokens = tuple(ansi[2:-1].split(";"))
    last = _last_reset_index(tokens)
    if last < 0:
        return interpret(tokens), False
    rest = tokens[last + 1 :]
    return (interpret(rest) if rest else None), True


_UNDERLINE_STYLES = {"0": "none", "1": "single", "2": "double", "3": "curly", "4": "dotted", "5": "dashed"}


def _colon_color(parts: list[str]) -> Optional[Color]:
    """Parse an ITU colon-form colour: 38:5:n or 38:2[:id]:r:g:b."""
    if len(parts) < 3:
        return None
    if parts[1] == "5":
        try:
            return Color("indexed", int(parts[2]))
        except ValueError:
            return None
    if parts[1] == "2":
        nums = [p for p in parts[2:] if p != ""]
        if len(nums) >= 3:
            try:
                return Color("rgb", (int(nums[-3]), int(nums[-2]), int(nums[-1])))
            except ValueError:
                return None
    return None


@lru_cache(maxsize=10000)
def interpret(tokens: Tuple[str, ...]) -> Style:
    style = Style()
    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Colon-subparameter forms: underline styles (4:n) and ITU colours (38:/48:/58:)
        if ":" in token:
            parts = token.split(":")
            head = parts[0]
            if head == "4":
                ul = _UNDERLINE_STYLES.get(parts[1] if len(parts) > 1 else "1", "single")
                if ul == "none":
                    style = replace(style, underline=False, underline_style=None)
                else:
                    style = replace(style, underline=True, underline_style=None if ul == "single" else ul)
            elif head in {"38", "48", "58"}:
                color = _colon_color(parts)
                if color is not None:
                    attr = {"38": "fg", "48": "bg", "58": "underline_color"}[head]
                    style = replace(style, **{attr: color})
            i += 1
            continue

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
        elif token == "5" or token == "6":  # 6 = rapid blink; rendered the same
            style = replace(style, blink=True)
        elif token == "7":
            style = replace(style, reverse=True)
        elif token == "8":
            style = replace(style, conceal=True)
        elif token == "9":
            style = replace(style, strike=True)

        elif token in ("10", "11", "12", "13", "14", "15", "16", "17", "18", "19"):
            style = replace(style, font=int(token) - 10)
        elif token == "20":
            style = replace(style, fraktur=True)
        elif token == "22":
            style = replace(style, bold=False, dim=False)
        elif token == "23":
            style = replace(style, italic=False, fraktur=False)
        elif token == "21":
            style = replace(style, underline=True, underline_style="double")
        elif token == "24":
            style = replace(style, underline=False, underline_style=None)
        elif token == "25":
            style = replace(style, blink=False)
        elif token == "27":
            style = replace(style, reverse=False)
        elif token == "28":
            style = replace(style, conceal=False)
        elif token == "29":
            style = replace(style, strike=False)
        elif token == "51":
            style = replace(style, framed=True)
        elif token == "52":
            style = replace(style, encircled=True)
        elif token == "53":
            style = replace(style, overline=True)
        elif token == "54":
            style = replace(style, framed=False, encircled=False)
        elif token == "55":
            style = replace(style, overline=False)
        elif token == "59":
            style = replace(style, underline_color=Color("default"))
        elif token in ("60", "61", "62", "63", "64"):
            style = replace(
                style,
                ideogram={
                    "60": "underline",
                    "61": "double_underline",
                    "62": "overline",
                    "63": "double_overline",
                    "64": "stress",
                }[token],
            )
        elif token == "65":
            style = replace(style, ideogram="none")

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
        elif token in {"38", "48", "58"}:
            attr = {"38": "fg", "48": "bg", "58": "underline_color"}[token]
            if i + 1 < len(tokens):
                mode = tokens[i + 1]
                if mode == "5" and i + 2 < len(tokens):
                    style = replace(style, **{attr: Color("indexed", int(tokens[i + 2]))})
                    i += 2
                elif mode == "2" and i + 4 < len(tokens):
                    r, g, b = int(tokens[i + 2]), int(tokens[i + 3]), int(tokens[i + 4])
                    style = replace(style, **{attr: Color("rgb", (r, g, b))})
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
    if style.bg is None or style.bg.mode == "default":
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
    if new and ("\x1b[0m" in new or "\x1b[00m" in new or "\x1b[m" in new):
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
        params.append(
            {"double": "21", "curly": "4:3", "dotted": "4:4", "dashed": "4:5"}.get(style.underline_style, "4")
        )
    if style.blink is True:
        params.append("5")
    if style.reverse is True:
        params.append("7")
    if style.conceal is True:
        params.append("8")
    if style.strike is True:
        params.append("9")
    if style.fraktur is True:
        params.append("20")
    if style.font is not None:
        params.append("10" if style.font == 0 else str(10 + style.font))
    if style.framed is True:
        params.append("51")
    if style.encircled is True:
        params.append("52")
    if style.overline is True:
        params.append("53")
    if style.ideogram is not None:
        params.append(
            {
                "underline": "60",
                "double_underline": "61",
                "overline": "62",
                "double_overline": "63",
                "stress": "64",
                "none": "65",
            }[style.ideogram]
        )

    # Foreground color
    if style.fg is not None:
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
    if style.bg is not None:
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

    # Underline color
    if style.underline_color is not None:
        uc = style.underline_color
        if uc.mode == "indexed":
            params.append(f"58;5;{uc.value}")
        elif uc.mode == "rgb":
            r, g, b = uc.value
            params.append(f"58;2;{r};{g};{b}")
        elif uc.mode == "default":
            params.append("59")

    if not params:
        return ""

    return f"\x1b[{';'.join(params)}m"
