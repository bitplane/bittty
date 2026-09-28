"""Terminal models: the emulation profile as data.

A model captures the constants that distinguish one real terminal from
another — starting with the Device Attributes (DA) responses used to identify
the terminal to the host. Over time this grows to carry charset repertoire,
colour depth, and which capabilities a board assembles.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .keymap import (
    BITTTY_KEYMAP,
    LINUX_KEYMAP,
    SCREEN_KEYMAP,
    TMUX_KEYMAP,
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
    VT102_MODE_CAPABILITIES,
    VT220_MODE_CAPABILITIES,
    VT320_MODE_CAPABILITIES,
    VT420_MODE_CAPABILITIES,
    VT510_MODE_CAPABILITIES,
    VTE_MODE_CAPABILITIES,
    XTERM_MODE_CAPABILITIES,
)
from .options import (
    DEC_LINE_EDITING,
    EDITING,
    DEC_DISPLAYED_EXTENT,
    DEC_EXTENDED_CPR,
    DEC_KEY_MEMORY,
    DEC_KEYBOARD_DIALECT,
    DEC_KEYBOARD_LEDS,
    DEC_PRINTER_PORT,
    DEC_STATUS_LINE,
    DEC_TERMINAL_STATE,
    DEC_UPSS,
    DEC_USER_KEYS,
    KITTY_KEYBOARD,
    LOCATOR_PORT,
    NO_PRINTER,
    VT510_COMM_PORTS,
    VT510_PRINTER_PORT,
    XTERM_EXTRAS,
    XTERM_MODIFY_KEYS,
    XTERM_PASTE,
    XTERM_PRINTER_PIPE,
    Option,
    PrinterCapabilities,
)
from .palette import VGA_PALETTE, XTERM_PALETTE, PaletteDefaults


def _fixed(status: int, *modes: str) -> frozenset[tuple[bool, int, int]]:
    """Modes reported permanently set (3) or reset (4); "?n" names a private mode."""
    return frozenset((mode.startswith("?"), int(mode.lstrip("?")), status) for mode in modes)


# The ECMA-48 modes DEC terminals (and xterm) never implemented: GATM, SRTM, VEM, HEM, PUM,
# FEAM, FETM, MATM, TTM, SATM, TSM and EBM, permanently reset (VT420 user guide table 9-2).
# CRM (show controls): "The host cannot change the setting of CRM. You can only change CRM
# from set-up" (VT320 and VT420 user guides); bittty has no Set-Up, so it stays reset.
SET_UP_CRM = _fixed(2, "3")
UNIMPLEMENTED_ANSI_MODES = _fixed(4, "1", "5", "7", "10", "11", "13", "14", "15", "16", "17", "18", "19")


# The xterm resources it reports but the host cannot set: cursor blink, utf8, cjkWidth,
# emojiWidth and privateWidth (xterm 407's values).
XTERM_READ_ONLY_RESOURCES = _fixed(2, "?13", "?1021", "?1022") | _fixed(1, "?1020", "?1023")


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
    # Non-mode control functions in the model's own software (e.g. the kitty
    # keyboard protocol), as opposed to being contributed by a fitted option.
    control_capabilities: frozenset[str] = EDITING
    # DEC hardware uses 0 for a valid DECRQSS request; modern emulators use 1.
    decrqss_valid_is_one: bool = True
    udk_capacity: int = 4096  # byte budget for downloaded function-key strings
    # Private-mode registers this terminal sets at power-on (and RIS), beyond each mode's own
    # default. A register outside the mode repertoire is fixed: the host cannot change it.
    power_on_modes: frozenset[int] = frozenset()
    # DECSSDT at power-on and RIS (0 none, 1 indicator); the status line needs DEC_STATUS_LINE.
    status_line_type: int = 0
    # Bytes of macro memory (DECDMAC); None: no macro reports at all. xterm answers with none.
    macro_space: int | None = None
    # The user-preferred supplemental set at power-on (DECRQUPSS); None: no such report.
    upss: str | None = None
    # The keyboard DSR's Ptyp for a VT and an enhanced PC layout; () is the VT220's report of
    # the language alone, and None no report at all.
    keyboard_types: tuple[int, ...] | None = None
    # Modes the host cannot change, as (private, number, status): DECRQM reports them
    # permanently set (3) or reset (4).
    fixed_modes: frozenset[tuple[bool, int, int]] = frozenset()
    # Minutes without activity before the screen blanks at power-on; 0 never (the VT510's CRT saver).
    blank_timeout: int = 0
    # Whether resizing re-wraps soft-wrapped lines (VTE and kitty always do).
    reflows: bool = False
    # Page memory as (lines per page, pages) pairs; a page size not listed has one page (DECSLPP).
    page_memory: tuple[tuple[int, int], ...] = ()

    @property
    def capabilities(self) -> frozenset[str]:
        """Everything this terminal implements: its own repertoire plus its options."""
        if not self.options:
            return self.mode_capabilities
        return self.mode_capabilities.union(*(option.mode_capabilities for option in self.options))

    @property
    def provides(self) -> frozenset[str]:
        """Non-mode capabilities: the model's own plus its installed options'."""
        if not self.options:
            return self.control_capabilities
        return self.control_capabilities.union(*(option.provides for option in self.options))

    def pages_for(self, lines: int) -> int:
        """How many pages of this height page memory holds."""
        return dict(self.page_memory).get(lines, 1)

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
    control_capabilities=EDITING
    | frozenset(
        {DEC_KEYBOARD_LEDS, DEC_USER_KEYS, XTERM_MODIFY_KEYS, XTERM_EXTRAS, DEC_DISPLAYED_EXTENT, DEC_EXTENDED_CPR}
        | {XTERM_PASTE}
    ),
    power_on_modes=frozenset({1034}),  # eightBitInput
    # Captured from xterm 407: DEC modes it knows but cannot change, and its one permanent set.
    fixed_modes=UNIMPLEMENTED_ANSI_MODES
    | _fixed(4, "?8", "?10", "?11", "?16", "?46", "?53", "?59", "?60", "?61", "?64", "?68", "?73", "?81")
    | _fixed(3, "?14")
    | _fixed(2, "3", "?80", "?8452")  # CRM, and the sixel modes of a build without sixel
    | _fixed(1, "?1070")
    | XTERM_READ_ONLY_RESOURCES,
    # The sets of xterm's default VT4xx level (charproc.c scs_table): not the VT100's
    # alternate ROMs nor JIS Roman, nor the VT5xx sets.
    charsets=frozenset(
        {"B", "A", "0", "<", "%5", ">", "96A", "%6", "4", "5", "C", "R", "f", "Q", "9", "K", "Y", "E", "6", "`"}
        | {"Z", "7", "H", "="}
    ),
    macro_space=0,  # xterm 407 reports no macro space
    keyboard_types=(0, 0),
    upss="B",  # xterm has no user-preferred set in UTF-8 and reports ASCII (charproc.c)
)

BITTTY = Model(
    name="bittty",
    da1_response="\033[?62;1;2;6;8;9;15;18;21;22;23c",
    term_name="xterm",
    da2_response=XTERM.da2_response,
    mode_capabilities=BITTTY_MODE_CAPABILITIES,
    keymap=BITTTY_KEYMAP,
    options=frozenset({VT510_PRINTER_PORT, VT510_COMM_PORTS, LOCATOR_PORT}),
    control_capabilities=EDITING
    | frozenset(
        {
            KITTY_KEYBOARD,
            DEC_KEYBOARD_LEDS,
            DEC_USER_KEYS,
            XTERM_MODIFY_KEYS,
            DEC_STATUS_LINE,
            XTERM_EXTRAS,
            DEC_DISPLAYED_EXTENT,
            DEC_UPSS,
            DEC_TERMINAL_STATE,
            DEC_KEYBOARD_DIALECT,
            DEC_KEY_MEMORY,
            DEC_EXTENDED_CPR,
        }
    ),
    power_on_modes=frozenset({1036, 1039, 2028}),  # Alt and Meta send ESC; text reflow
    fixed_modes=XTERM_READ_ONLY_RESOURCES,
    macro_space=6144,
    upss="%5",
    keyboard_types=(4, 5),
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
    control_capabilities=frozenset(),  # the editing functions arrived with the VT102
)

VT102 = Model(
    name="vt102",
    da1_response="\033[?6c",  # VT102 user guide
    da2_response=None,
    da3_response=None,
    mode_capabilities=VT102_MODE_CAPABILITIES,
    charsets=VT100.charsets,
    color_depth="monochrome",
    keymap=VT100_KEYMAP,
    options=frozenset({DEC_PRINTER_PORT}),
    control_capabilities=frozenset({DEC_LINE_EDITING}),  # IL, DL and DCH; ICH and ECH came with the VT220
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
    control_capabilities=EDITING | {DEC_USER_KEYS},
    udk_capacity=256,
    keyboard_types=(),
)

# VT320 and VT420 from their user guides' control-sequence references (EK-VT320-UU-001,
# EK-VT420-UU-002). The soft character set (DA 7) is left out of DA, as bittty has none;
# as with the VT220 and VT510, the firmware version in secondary DA is a stand-in.
VT320 = Model(
    name="vt320",
    da1_response="\033[?63;1;2;6;8;9c",
    da2_response="\033[>24;10;0c",
    da3_response=None,
    mode_capabilities=VT320_MODE_CAPABILITIES,
    charsets=VT220.charsets | {"%5", ">", "96A", "9", "`", "%6"},
    color_depth="monochrome",
    keymap=VT220_KEYMAP,
    options=frozenset({DEC_PRINTER_PORT}),
    control_capabilities=EDITING | {DEC_USER_KEYS, DEC_STATUS_LINE, DEC_UPSS, DEC_TERMINAL_STATE},
    decrqss_valid_is_one=False,
    upss="%5",
    keyboard_types=(),  # the language alone, as the VT220 reports it
    fixed_modes=_fixed(4, "10") | SET_UP_CRM,  # HEM
    power_on_modes=frozenset({4}),  # smooth scroll
)

VT420 = Model(
    name="vt420",
    da1_response="\033[?64;1;2;6;8;9;15;18;21c",  # not 19: bittty has one session
    da2_response="\033[>41;10;0c",
    mode_capabilities=VT420_MODE_CAPABILITIES,
    charsets=VT320.charsets,
    color_depth="monochrome",
    keymap=VT220_KEYMAP,
    options=frozenset({DEC_PRINTER_PORT}),
    control_capabilities=EDITING
    | {
        DEC_USER_KEYS,
        DEC_STATUS_LINE,
        DEC_UPSS,
        DEC_TERMINAL_STATE,
        DEC_DISPLAYED_EXTENT,
        DEC_EXTENDED_CPR,
    },
    decrqss_valid_is_one=False,
    upss="%5",
    keyboard_types=(1, 1),  # LK401
    macro_space=6144,  # the VT510's figure: the VT420 guide does not give one
    page_memory=((24, 6), (25, 5), (36, 4), (48, 3), (72, 2)),  # a single session
    fixed_modes=UNIMPLEMENTED_ANSI_MODES | SET_UP_CRM | _fixed(4, "?60"),  # DECHCCM
    power_on_modes=frozenset({4}),  # smooth scroll
)

VT510 = Model(
    name="vt510",
    da1_response="\033[?64;1;2;7;8;9;15;18;21;44;45;46c",
    da2_response="\033[>61;10;0c",
    da3_response=None,
    mode_capabilities=VT510_MODE_CAPABILITIES,
    charsets=VT220.charsets
    | {"%5", ">", "f", "9", "`", "96A", "96B", "96F", "96H", "96L", "96M"}
    | {"&4", '"?', '"4', "%0", '">', "%=", "&5", "%3", "%2"},  # the VT5xx sets
    color_depth="monochrome",
    keymap=VT220_KEYMAP,
    options=frozenset({VT510_PRINTER_PORT, VT510_COMM_PORTS}),
    control_capabilities=EDITING
    | frozenset(
        {
            DEC_KEYBOARD_LEDS,
            DEC_USER_KEYS,
            DEC_STATUS_LINE,
            DEC_DISPLAYED_EXTENT,
            DEC_UPSS,
            DEC_TERMINAL_STATE,
            DEC_KEYBOARD_DIALECT,
            DEC_KEY_MEMORY,
            DEC_EXTENDED_CPR,
        }
    ),
    decrqss_valid_is_one=False,
    status_line_type=1,  # the indicator, the Set-Up default
    page_memory=((24, 3), (25, 2), (36, 2)),  # DECSLPP; any other page size is a single page
    fixed_modes=UNIMPLEMENTED_ANSI_MODES | SET_UP_CRM | _fixed(4, "?60"),  # as the VT420
    power_on_modes=frozenset({4}),  # smooth scroll
    macro_space=6144,  # "6 Kbytes of memory available for the storage of macros"
    upss="%5",
    keyboard_types=(4, 5),  # LK450, PCXAL
    blank_timeout=30,  # DECCRTSM: the CRT saver is enabled by default
    udk_capacity=804,  # the programmable keys' memory, which DECUDK shares
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
    power_on_modes=frozenset({1036, 1039}),  # keyboard.c KBD_DEFMODE sets VC_META: Alt sends ESC
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
    keymap=TMUX_KEYMAP,
    power_on_modes=frozenset({1036, 1039}),  # Alt/Meta is always an ESC prefix
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
    reflows=True,
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
    control_capabilities=EDITING | {KITTY_KEYBOARD},
    reflows=True,
    power_on_modes=frozenset({1036, 1039}),  # legacy text keys: Alt sends ESC
)

DEFAULT = BITTTY

# Resolve a $TERM name to a model (see get_model).
PERSONALITIES: dict[str, Model] = {
    "bittty": BITTTY,
    "xterm": XTERM,
    "xterm-256color": XTERM,
    "vt100": VT100,
    "vt102": VT102,
    "vt220": VT220,
    "vt320": VT320,
    "vt420": VT420,
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
