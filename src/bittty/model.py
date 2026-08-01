"""Terminal models: the emulation profile as data.

A model captures the constants that distinguish one real terminal from
another — starting with the Device Attributes (DA) responses used to identify
the terminal to the host. Over time this grows to carry charset repertoire,
colour depth, and which capabilities a board assembles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .keymap import (
    LINUX_KEYMAP,
    SCREEN_KEYMAP,
    URXVT_KEYMAP,
    VT100_KEYMAP,
    VT220_KEYMAP,
    XTERM_KEYMAP,
    KeyMap,
)
from .mode_profiles import (
    BITTTY_MODE_CAPABILITIES,
    KITTY_MODE_CAPABILITIES,
    LINUX_MODE_CAPABILITIES,
    SCREEN_MODE_CAPABILITIES,
    TMUX_MODE_CAPABILITIES,
    URXVT_MODE_CAPABILITIES,
    VT100_MODE_CAPABILITIES,
    VT220_MODE_CAPABILITIES,
    VT510_MODE_CAPABILITIES,
    VTE_MODE_CAPABILITIES,
    XTERM_MODE_CAPABILITIES,
)
from .options import (
    DEC_PRINTER_PORT,
    LOCATOR_PORT,
    NO_PRINTER,
    VT510_PRINTER_PORT,
    XTERM_PRINTER_PIPE,
    Option,
    PrinterCapabilities,
)
from .palette import VGA_PALETTE, XTERM_PALETTE, PaletteDefaults


@dataclass(frozen=True)
class Model:
    """A terminal type expressed as data."""

    name: str
    da1_response: str  # Primary Device Attributes (answer to CSI c)
    da2_response: str | None = None  # Secondary DA (CSI > c); None if unsupported
    da3_response: str | None = "\033P!|00000000\033\\"  # Tertiary DA (CSI = c); None if unsupported
    # Backward-compatible subtractive override for custom Model callers.
    unsupported_modes: frozenset[tuple[bool, int]] = frozenset()
    # Default colours (16 ANSI + fg/bg/cursor) this terminal presents.
    palette: PaletteDefaults = field(default=XTERM_PALETTE)
    # Charset designators this terminal recognises for SCS; None means "all".
    charsets: frozenset[str] | None = None
    # Informational colour depth: "monochrome", "16", "256", or "truecolor".
    color_depth: str = "truecolor"
    # How this terminal encodes function keys and keyboard modifiers.
    keymap: KeyMap = field(default=XTERM_KEYMAP)
    # Semantic mode implementations this model assembles. Positive profiles
    # allow different terminal families to give the same number different meanings.
    mode_capabilities: frozenset[str] = BITTTY_MODE_CAPABILITIES
    # TERM-compatible name reported by XTGETTCAP; defaults to the model name.
    term_name: str | None = None
    # Hardware fitted at power-on; contributes to the repertoire below.
    options: frozenset[Option] = field(default_factory=frozenset)
    # DEC hardware uses 0 for a valid DECRQSS request; modern emulators use 1.
    decrqss_valid_is_one: bool = True

    @property
    def capabilities(self) -> frozenset[str]:
        """Everything this terminal implements: its own repertoire plus its options."""
        if not self.options:
            return self.mode_capabilities
        return self.mode_capabilities.union(*(option.mode_capabilities for option in self.options))

    @property
    def provides(self) -> frozenset[str]:
        """Non-mode capabilities contributed by installed options."""
        if not self.options:
            return frozenset()
        return frozenset().union(*(option.provides for option in self.options))

    @property
    def printer_capabilities(self) -> PrinterCapabilities:
        """The printer repertoire of the installed port, if one is fitted."""
        for option in self.options:
            if option.printer is not None:
                return option.printer
        return NO_PRINTER


# Primary DA responses per vt100.net / xterm ctlseqs.
XTERM = Model(
    name="xterm",
    da1_response="\033[?62;1;6;8;9;15;18;21;22;23c",
    da2_response="\033[>1;10;0c",
    mode_capabilities=XTERM_MODE_CAPABILITIES,
    options=frozenset({XTERM_PRINTER_PIPE, LOCATOR_PORT}),
)

BITTTY = Model(
    name="bittty",
    da1_response="\033[?62;1;2;6;8;9;15;18;21;22;23c",
    term_name="xterm",
    da2_response=XTERM.da2_response,
    mode_capabilities=BITTTY_MODE_CAPABILITIES,
    options=frozenset({VT510_PRINTER_PORT, LOCATOR_PORT}),
)

VT100 = Model(
    name="vt100",
    da1_response="\033[?1;2c",  # VT100 with Advanced Video Option
    da2_response=None,  # secondary DA was introduced with the VT220
    da3_response=None,
    mode_capabilities=VT100_MODE_CAPABILITIES,
    # VT100 knows ASCII, UK, DEC Special Graphics and the alternate ROM sets;
    # DEC Supplemental and the national replacement sets arrived with the VT220.
    charsets=frozenset({"B", "A", "0", "1", "2"}),
    color_depth="monochrome",
    keymap=VT100_KEYMAP,
)

VT220 = Model(
    name="vt220",
    da1_response="\033[?62;1;2;6;8;9c",
    da2_response="\033[>1;10;0c",
    da3_response=None,
    mode_capabilities=VT220_MODE_CAPABILITIES,
    # VT220 adds DEC Supplemental ("<") and the national replacement sets over
    # the VT100, but DEC Technical (">") is a later (VT240/VT330) charset.
    charsets=frozenset(
        {"B", "A", "0", "1", "2", "<", "4", "5", "6", "7", "=", "C", "E", "H", "J", "K", "Q", "R", "Y", "Z", "%6"}
    ),
    color_depth="monochrome",
    keymap=VT220_KEYMAP,
    options=frozenset({DEC_PRINTER_PORT}),
)

VT510 = Model(
    name="vt510",
    da1_response="\033[?64;1;2;7;8;9;15;18;21;44;45;46c",
    da2_response="\033[>61;10;0c",
    da3_response=None,
    mode_capabilities=VT510_MODE_CAPABILITIES,
    charsets=VT220.charsets,
    color_depth="monochrome",
    keymap=VT220_KEYMAP,
    options=frozenset({VT510_PRINTER_PORT}),
    decrqss_valid_is_one=False,
)

LINUX = Model(
    name="linux",
    da1_response="\033[?6c",  # the linux console identifies as a VT102
    da2_response=None,
    da3_response=None,
    mode_capabilities=LINUX_MODE_CAPABILITIES,
    charsets=frozenset({"B", "A", "0", "U"}),
    color_depth="256",
    palette=VGA_PALETTE,
    keymap=LINUX_KEYMAP,
)

# GNU screen — a VT100+AVO emulator; keymap and colours from terminfo (screen-256color).
# DA1 is the standard VT100-with-AVO reply; DA2 type 83 = 'S' (the screen/tmux/urxvt S/T/U
# pattern, with tmux=84 confirmed against a live session). Version field unverified.
SCREEN = Model(
    name="screen",
    da1_response="\033[?1;2c",
    da2_response="\033[>83;0;0c",
    da3_response=None,
    mode_capabilities=SCREEN_MODE_CAPABILITIES,
    color_depth="256",
    keymap=SCREEN_KEYMAP,
)

# tmux — live-verified against a running tmux: DA1 ?1;2;4c (VT100+AVO, and it advertises
# sixel — code 4 — for whatever it fronts), DA2 type 84 = 'T'. Shares screen's keymap.
TMUX = Model(
    name="tmux",
    da1_response="\033[?1;2;4c",
    da2_response="\033[>84;0;0c",
    da3_response=None,
    mode_capabilities=TMUX_MODE_CAPABILITIES,
    color_depth="256",
    keymap=SCREEN_KEYMAP,
)

# rxvt-unicode — keymap and colours from terminfo (rxvt-unicode-256color). DA1 is VT100+AVO;
# DA2 type 85 = 'U' (S/T/U pattern). Version field unverified.
URXVT = Model(
    name="rxvt-unicode",
    da1_response="\033[?1;2c",
    da2_response="\033[>85;0;0c",
    da3_response=None,
    mode_capabilities=URXVT_MODE_CAPABILITIES,
    color_depth="256",
    keymap=URXVT_KEYMAP,
)

# GNOME Terminal / VTE — live-verified against gnome-terminal (VTE 0.84): DA1 reports
# level 61 with ANSI colour (22) and rectangular editing (28); DA2 type 61 carries the
# VTE version in the firmware field (8400). Truecolour, xterm-family keymap.
GNOME = Model(
    name="gnome",
    da1_response="\033[?61;1;21;22;28c",
    da2_response="\033[>61;8400;1c",
    da3_response=None,
    mode_capabilities=VTE_MODE_CAPABILITIES,
    color_depth="truecolor",
    keymap=XTERM_KEYMAP,
)

# kitty — live-verified (TERM=xterm-kitty). DA2 firmware field 4000 is the kitty version
# (0.40). DA1 as captured. Truecolour; xterm-family base keymap, plus the Kitty keyboard
# protocol handled by the keyboard device.
KITTY = Model(
    name="kitty",
    da1_response="\033[?62;52;c",
    da2_response="\033[>1;4000;45c",
    da3_response=None,
    mode_capabilities=KITTY_MODE_CAPABILITIES,
    color_depth="truecolor",
    keymap=XTERM_KEYMAP,
)

DEFAULT = BITTTY

# Resolve a $TERM name to a model (see get_model).
PERSONALITIES: dict[str, Model] = {
    "bittty": BITTTY,
    "xterm": XTERM,
    "xterm-256color": XTERM,
    "vt100": VT100,
    "vt102": VT100,
    "vt220": VT220,
    "vt510": VT510,
    "linux": LINUX,
    "screen": SCREEN,
    "screen-256color": SCREEN,
    "tmux": TMUX,
    "tmux-256color": TMUX,
    "rxvt": URXVT,
    "rxvt-unicode": URXVT,
    "rxvt-unicode-256color": URXVT,
    "gnome": GNOME,
    "gnome-256color": GNOME,
    "vte": GNOME,
    "vte-256color": GNOME,
    "kitty": KITTY,
    "xterm-kitty": KITTY,
}


def get_model(term_name: str | None, default: Model = DEFAULT) -> Model:
    """Resolve a $TERM name to a model, falling back through shorter prefixes.

    So "xterm-kitty" or "screen.xterm-256color" degrade gracefully to the nearest
    known family, and an unknown or empty TERM yields the native BITTTY model.
    """
    name = term_name or ""
    while name:
        if name in PERSONALITIES:
            return PERSONALITIES[name]
        if "-" in name:
            name = name.rsplit("-", 1)[0]
        else:
            break
    return default
