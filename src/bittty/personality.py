"""Terminal personalities: the emulation profile as data.

A personality captures the constants that distinguish one real terminal from
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
from .palette import VGA_PALETTE, XTERM_PALETTE, PaletteDefaults


@dataclass(frozen=True)
class Personality:
    """A terminal type expressed as data."""

    name: str
    da1_response: str  # Primary Device Attributes (answer to CSI c)
    da2_response: str | None = None  # Secondary DA (CSI > c); None if unsupported
    da3_response: str | None = "\033P!|00000000\033\\"  # Tertiary DA (CSI = c); None if unsupported
    # Modes this terminal does not recognise, as (private, number) keys.
    unsupported_modes: frozenset[tuple[bool, int]] = frozenset()
    # Default colours (16 ANSI + fg/bg/cursor) this terminal presents.
    palette: PaletteDefaults = field(default=XTERM_PALETTE)
    # Charset designators this terminal recognises for SCS; None means "all".
    charsets: frozenset[str] | None = None
    # Informational colour depth: "monochrome", "16", "256", or "truecolor".
    color_depth: str = "truecolor"
    # How this terminal encodes function keys and keyboard modifiers.
    keymap: KeyMap = field(default=XTERM_KEYMAP)


# Primary DA responses per vt100.net / xterm ctlseqs.
XTERM = Personality(
    name="xterm",
    da1_response="\033[?62;1;6;8;9;15;18;21;22;23c",
    da2_response="\033[>1;10;0c",
)

VT100 = Personality(
    name="vt100",
    da1_response="\033[?1;2c",  # VT100 with Advanced Video Option
    da2_response=None,  # secondary DA was introduced with the VT220
    da3_response=None,
    # A VT100 predates xterm-era private modes such as bracketed paste (2004)
    # and SGR mouse reporting (1006), and has no notion of bittty's auto-resize
    # (2028); it does not recognise any of them.
    unsupported_modes=frozenset({(True, 2004), (True, 1006), (True, 2028)}),
    # VT100 knows ASCII, UK, DEC Special Graphics and the alternate ROM sets;
    # DEC Supplemental and the national replacement sets arrived with the VT220.
    charsets=frozenset({"B", "A", "0", "1", "2"}),
    color_depth="monochrome",
    keymap=VT100_KEYMAP,
)

VT220 = Personality(
    name="vt220",
    da1_response="\033[?62;1;2;6;8;9c",
    da2_response="\033[>1;10;0c",
    da3_response=None,
    # The VT220 predates mouse tracking, the alternate screen buffer, bracketed
    # paste, and bittty's auto-resize; none of those private modes exist for it.
    unsupported_modes=frozenset(
        {
            (True, 9),
            (True, 1000),
            (True, 1002),
            (True, 1003),
            (True, 1006),
            (True, 1015),
            (True, 47),
            (True, 1047),
            (True, 1048),
            (True, 1049),
            (True, 2004),
            (True, 2028),
        }
    ),
    # VT220 adds DEC Supplemental ("<") and the national replacement sets over
    # the VT100, but DEC Technical (">") is a later (VT240/VT330) charset.
    charsets=frozenset(
        {"B", "A", "0", "1", "2", "<", "4", "5", "6", "7", "=", "C", "E", "H", "J", "K", "Q", "R", "Y", "Z", "%6"}
    ),
    color_depth="monochrome",
    keymap=VT220_KEYMAP,
)

LINUX = Personality(
    name="linux",
    da1_response="\033[?6c",  # the linux console identifies as a VT102
    da2_response=None,
    da3_response=None,
    # No mouse tracking or bracketed paste on the bare console.
    unsupported_modes=frozenset(
        {
            (True, 9),
            (True, 1000),
            (True, 1002),
            (True, 1003),
            (True, 1006),
            (True, 1015),
            (True, 2004),
        }
    ),
    charsets=frozenset({"B", "A", "0", "U"}),
    color_depth="256",
    palette=VGA_PALETTE,
    keymap=LINUX_KEYMAP,
)

# GNU screen — a VT100+AVO emulator; keymap and colours from terminfo (screen-256color).
# DA1 is the standard VT100-with-AVO reply; DA2 type 83 = 'S' (the screen/tmux/urxvt S/T/U
# pattern, with tmux=84 confirmed against a live session). Version field unverified.
SCREEN = Personality(
    name="screen",
    da1_response="\033[?1;2c",
    da2_response="\033[>83;0;0c",
    da3_response=None,
    color_depth="256",
    keymap=SCREEN_KEYMAP,
)

# tmux — live-verified against a running tmux: DA1 ?1;2;4c (VT100+AVO, and it advertises
# sixel — code 4 — for whatever it fronts), DA2 type 84 = 'T'. Shares screen's keymap.
TMUX = Personality(
    name="tmux",
    da1_response="\033[?1;2;4c",
    da2_response="\033[>84;0;0c",
    da3_response=None,
    color_depth="256",
    keymap=SCREEN_KEYMAP,
)

# rxvt-unicode — keymap and colours from terminfo (rxvt-unicode-256color). DA1 is VT100+AVO;
# DA2 type 85 = 'U' (S/T/U pattern). Version field unverified.
URXVT = Personality(
    name="rxvt-unicode",
    da1_response="\033[?1;2c",
    da2_response="\033[>85;0;0c",
    da3_response=None,
    color_depth="256",
    keymap=URXVT_KEYMAP,
)

# GNOME Terminal / VTE — live-verified against gnome-terminal (VTE 0.84): DA1 reports
# level 61 with ANSI colour (22) and rectangular editing (28); DA2 type 61 carries the
# VTE version in the firmware field (8400). Truecolour, xterm-family keymap.
GNOME = Personality(
    name="gnome",
    da1_response="\033[?61;1;21;22;28c",
    da2_response="\033[>61;8400;1c",
    da3_response=None,
    color_depth="truecolor",
    keymap=XTERM_KEYMAP,
)

DEFAULT = XTERM

# Resolve a $TERM name to a personality (see get_personality).
PERSONALITIES: dict[str, Personality] = {
    "xterm": XTERM,
    "xterm-256color": XTERM,
    "vt100": VT100,
    "vt102": VT100,
    "vt220": VT220,
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
}


def get_personality(term_name: str | None, default: Personality = DEFAULT) -> Personality:
    """Resolve a $TERM name to a personality, falling back through shorter prefixes.

    So "xterm-kitty" or "screen.xterm-256color" degrade gracefully to the nearest
    known family, and an unknown or empty TERM yields the default (xterm).
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
