from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

# --- Constants --- #

CURSOR_CODE = "\033[7m"  # Reverse video for cursor display
RESET_CODE = "\033[0m"  # Reset all formatting


# --- Color Model --- #


@dataclass(frozen=True, slots=True)
class Color:
    mode: Literal["default", "indexed", "rgb"]
    value: int | tuple[int, int, int] | None = None

    @property
    def ansi(self) -> str:
        if self.mode == "default":
            return ""
        if self.mode == "indexed":
            return f"5;{self.value}"
        if self.mode == "rgb":
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
#
# The tri-state attributes (None = inherit / True / False, plus the small enums)
# live packed in two ints: _set is the coverage mask saying which bits carry an
# explicit value, _val holds the values in the same bit positions. Multi-bit
# fields set their whole span in _set, so merge() needs no per-field branching:
#     set = a._set | b._set
#     val = (b._val & b._set) | (a._val & ~b._set)

_BOLD = 1 << 0
_DIM = 1 << 1
_ITALIC = 1 << 2
_UNDERLINE = 1 << 3
_BLINK = 1 << 4
_REVERSE = 1 << 5
_CONCEAL = 1 << 6
_STRIKE = 1 << 7
_OVERLINE = 1 << 8
_FRAKTUR = 1 << 9
_FRAMED = 1 << 10
_ENCIRCLED = 1 << 11
_PROTECTED = 1 << 12
_FONT_SHIFT, _FONT_MASK = 13, 0xF << 13
_ULSTYLE_SHIFT, _ULSTYLE_MASK = 17, 0x7 << 17
_IDEO_SHIFT, _IDEO_MASK = 20, 0x7 << 20

_ULSTYLES = (None, "double", "curly", "dotted", "dashed")  # index = packed value
_IDEOGRAMS = (None, "underline", "double_underline", "overline", "double_overline", "stress", "none")

_FIELD_NAMES = (
    "fg",
    "bg",
    "bold",
    "dim",
    "italic",
    "underline",
    "blink",
    "reverse",
    "conceal",
    "strike",
    "underline_style",
    "overline",
    "underline_color",
    "font",
    "fraktur",
    "framed",
    "encircled",
    "ideogram",
    "hyperlink",
    "hyperlink_id",
    "protected",
)


def _flag(mask):
    """A tri-state property over the packed ints: None when unset, else the bool."""

    def get(self):
        return (self._val & mask) != 0 if self._set & mask else None

    return property(get)


class Style:
    """Immutable text style. The keyword surface matches the old dataclass field
    per field (None = inherit); internally the tri-state attributes are packed
    so merge/eq/hash cost a couple of int ops instead of a 20-field walk."""

    __slots__ = ("_set", "_val", "bg", "fg", "hyperlink", "hyperlink_id", "underline_color")

    def __init__(
        self,
        fg: Color | None = None,
        bg: Color | None = None,
        bold: bool | None = None,
        dim: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        blink: bool | None = None,
        reverse: bool | None = None,
        conceal: bool | None = None,
        strike: bool | None = None,
        underline_style: str | None = None,  # None=single / "double" / "curly" / "dotted" / "dashed"
        overline: bool | None = None,
        underline_color: Color | None = None,
        font: int | None = None,  # SGR 10-19: 0 = primary, 1-9 = alternate fonts
        fraktur: bool | None = None,  # SGR 20 (blackletter)
        framed: bool | None = None,  # SGR 51
        encircled: bool | None = None,  # SGR 52
        ideogram: str | None = None,  # SGR 60-65 (see _IDEOGRAMS)
        hyperlink: str | None = None,  # OSC 8 target URI (not an SGR attribute)
        hyperlink_id: str | None = None,  # OSC 8 id= param: groups split link segments
        protected: bool | None = None,  # DECSCA: shielded from selective erase
    ) -> None:
        self.fg = fg
        self.bg = bg
        self.underline_color = underline_color
        self.hyperlink = hyperlink
        self.hyperlink_id = hyperlink_id
        s = v = 0
        for value, mask in (
            (bold, _BOLD),
            (dim, _DIM),
            (italic, _ITALIC),
            (underline, _UNDERLINE),
            (blink, _BLINK),
            (reverse, _REVERSE),
            (conceal, _CONCEAL),
            (strike, _STRIKE),
            (overline, _OVERLINE),
            (fraktur, _FRAKTUR),
            (framed, _FRAMED),
            (encircled, _ENCIRCLED),
            (protected, _PROTECTED),
        ):
            if value is not None:
                s |= mask
                if value:
                    v |= mask
        if font is not None:
            s |= _FONT_MASK
            v |= font << _FONT_SHIFT
        if underline_style is not None:
            s |= _ULSTYLE_MASK
            v |= _ULSTYLES.index(underline_style) << _ULSTYLE_SHIFT
        if ideogram is not None:
            s |= _IDEO_MASK
            v |= _IDEOGRAMS.index(ideogram) << _IDEO_SHIFT
        self._set = s
        self._val = v

    bold = _flag(_BOLD)
    dim = _flag(_DIM)
    italic = _flag(_ITALIC)
    underline = _flag(_UNDERLINE)
    blink = _flag(_BLINK)
    reverse = _flag(_REVERSE)
    conceal = _flag(_CONCEAL)
    strike = _flag(_STRIKE)
    overline = _flag(_OVERLINE)
    fraktur = _flag(_FRAKTUR)
    framed = _flag(_FRAMED)
    encircled = _flag(_ENCIRCLED)
    protected = _flag(_PROTECTED)

    @property
    def font(self) -> int | None:
        return (self._val & _FONT_MASK) >> _FONT_SHIFT if self._set & _FONT_MASK else None

    @property
    def underline_style(self) -> str | None:
        return _ULSTYLES[(self._val & _ULSTYLE_MASK) >> _ULSTYLE_SHIFT] if self._set & _ULSTYLE_MASK else None

    @property
    def ideogram(self) -> str | None:
        return _IDEOGRAMS[(self._val & _IDEO_MASK) >> _IDEO_SHIFT] if self._set & _IDEO_MASK else None

    def merge(self, other: Style) -> Style:
        """Merge another style into this one; the other's set attributes win."""
        new = Style.__new__(Style)
        o_set = other._set
        new._set = self._set | o_set
        new._val = (other._val & o_set) | (self._val & ~o_set)
        new.fg = other.fg if other.fg is not None else self.fg
        new.bg = other.bg if other.bg is not None else self.bg
        new.underline_color = other.underline_color if other.underline_color is not None else self.underline_color
        new.hyperlink = other.hyperlink if other.hyperlink is not None else self.hyperlink
        # The id travels with its link: keyed on other.hyperlink, not other.hyperlink_id
        new.hyperlink_id = other.hyperlink_id if other.hyperlink is not None else self.hyperlink_id
        return new

    def replace(self, **kwargs) -> Style:
        """A new Style with the given fields replaced (None = back to inherit)."""
        fields = {name: getattr(self, name) for name in _FIELD_NAMES}
        fields.update(kwargs)
        return Style(**fields)

    def diff(self, other: Style) -> str:
        """Generate minimal ANSI sequence to transition to another style."""
        return _style_diff(self, other)

    def __eq__(self, other: object) -> bool:
        if type(other) is not Style:
            return NotImplemented
        return (
            self._set == other._set
            and self._val == other._val
            and self.fg == other.fg
            and self.bg == other.bg
            and self.underline_color == other.underline_color
            and self.hyperlink == other.hyperlink
            and self.hyperlink_id == other.hyperlink_id
        )

    def __hash__(self) -> int:
        return hash((self._set, self._val, self.fg, self.bg, self.underline_color, self.hyperlink, self.hyperlink_id))

    def __repr__(self) -> str:
        parts = [f"{name}={getattr(self, name)!r}" for name in _FIELD_NAMES if getattr(self, name) is not None]
        return f"Style({', '.join(parts)})"


@lru_cache(maxsize=10000)
def _style_diff(a: Style, b: Style) -> str:
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


def _last_reset_index(tokens: tuple[str, ...]) -> int:
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
def parse_sgr_with_reset(ansi: str) -> tuple[Style | None, bool]:
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


def _colon_color(parts: list[str]) -> Color | None:
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


# Plain flag tokens: turn a mask on / explicitly off.
_TOKEN_ON = {
    "1": _BOLD,
    "01": _BOLD,
    "2": _DIM,
    "3": _ITALIC,
    "4": _UNDERLINE,
    "5": _BLINK,
    "6": _BLINK,  # rapid blink; rendered the same
    "7": _REVERSE,
    "8": _CONCEAL,
    "9": _STRIKE,
    "20": _FRAKTUR,
    "51": _FRAMED,
    "52": _ENCIRCLED,
    "53": _OVERLINE,
}
_TOKEN_OFF = {
    "22": _BOLD | _DIM,
    "23": _ITALIC | _FRAKTUR,
    "25": _BLINK,
    "27": _REVERSE,
    "28": _CONCEAL,
    "29": _STRIKE,
    "54": _FRAMED | _ENCIRCLED,
    "55": _OVERLINE,
}
_IDEOGRAM_TOKENS = {"60": 1, "61": 2, "62": 3, "63": 4, "64": 5, "65": 6}  # -> _IDEOGRAMS index
_COLOR_SLOTS = {"38": "fg", "48": "bg", "58": "underline_color"}


@lru_cache(maxsize=10000)
def interpret(tokens: tuple[str, ...]) -> Style:
    """Interpret SGR tokens into a Style, accumulating the packed masks directly."""
    s = v = 0
    colors = {"fg": None, "bg": None, "underline_color": None}
    i = 0
    while i < len(tokens):
        token = tokens[i]

        # Colon-subparameter forms: underline styles (4:n) and ITU colours (38:/48:/58:)
        if ":" in token:
            parts = token.split(":")
            head = parts[0]
            if head == "4":
                ul = _UNDERLINE_STYLES.get(parts[1] if len(parts) > 1 else "1", "single")
                s |= _UNDERLINE
                s &= ~_ULSTYLE_MASK
                v &= ~(_UNDERLINE | _ULSTYLE_MASK)
                if ul != "none":
                    v |= _UNDERLINE
                    if ul != "single":
                        s |= _ULSTYLE_MASK
                        v |= _ULSTYLES.index(ul) << _ULSTYLE_SHIFT
            elif head in _COLOR_SLOTS:
                color = _colon_color(parts)
                if color is not None:
                    colors[_COLOR_SLOTS[head]] = color
            i += 1
            continue

        if (mask := _TOKEN_ON.get(token)) is not None:
            s |= mask
            v |= mask
        elif (mask := _TOKEN_OFF.get(token)) is not None:
            s |= mask
            v &= ~mask
        elif token == "0" or token == "00":  # reset
            s = v = 0
            colors = {"fg": None, "bg": None, "underline_color": None}
        elif token == "21":  # double underline
            s |= _UNDERLINE | _ULSTYLE_MASK
            v = (v & ~_ULSTYLE_MASK) | _UNDERLINE | (_ULSTYLES.index("double") << _ULSTYLE_SHIFT)
        elif token == "24":  # underline off (and drop any underline style)
            s = (s | _UNDERLINE) & ~_ULSTYLE_MASK
            v &= ~(_UNDERLINE | _ULSTYLE_MASK)
        elif len(token) == 2 and token[0] == "1" and token.isdigit():  # 10-19: font select
            s |= _FONT_MASK
            v = (v & ~_FONT_MASK) | ((int(token) - 10) << _FONT_SHIFT)
        elif token == "59":
            colors["underline_color"] = Color("default")
        elif (ideo := _IDEOGRAM_TOKENS.get(token)) is not None:
            s |= _IDEO_MASK
            v = (v & ~_IDEO_MASK) | (ideo << _IDEO_SHIFT)
        elif token == "39":
            colors["fg"] = Color("default")
        elif token == "49":
            colors["bg"] = Color("default")
        elif (slot := _COLOR_SLOTS.get(token)) is not None:  # extended colour (indexed or rgb)
            if i + 1 < len(tokens):
                mode = tokens[i + 1]
                if mode == "5" and i + 2 < len(tokens):
                    colors[slot] = Color("indexed", int(tokens[i + 2]))
                    i += 2
                elif mode == "2" and i + 4 < len(tokens):
                    r, g, b = int(tokens[i + 2]), int(tokens[i + 3]), int(tokens[i + 4])
                    colors[slot] = Color("rgb", (r, g, b))
                    i += 4
        elif token.isdigit():
            n = int(token)
            if 30 <= n <= 37:
                colors["fg"] = Color("indexed", n - 30)
            elif 40 <= n <= 47:
                colors["bg"] = Color("indexed", n - 40)
            elif 90 <= n <= 97:
                colors["fg"] = Color("indexed", n - 90 + 8)
            elif 100 <= n <= 107:
                colors["bg"] = Color("indexed", n - 100 + 8)
        i += 1

    style = Style.__new__(Style)
    style._set = s
    style._val = v
    style.fg = colors["fg"]
    style.bg = colors["bg"]
    style.underline_color = colors["underline_color"]
    style.hyperlink = None
    style.hyperlink_id = None
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
    if style.bg.mode == "indexed":
        if style.bg.value < 8:
            return f"\x1b[{40 + style.bg.value}m"
        if style.bg.value < 16:
            return f"\x1b[{100 + style.bg.value - 8}m"
        return f"\x1b[48;5;{style.bg.value}m"
    if style.bg.mode == "rgb":
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
