"""Keyboard encoding as model data.

Function keys are where real terminals diverge most: a VT100 has only PF1-PF4
and no keyboard-modifier encoding, while xterm sends F1-F12 and folds shift/alt/
ctrl into a ``;mod`` parameter. A `KeyMap` captures that difference as data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

ESC = "\x1b"

# The application/numeric keypad is standard across the terminals modelled here.
_NUMPAD_NUMERIC = {str(d): str(d) for d in range(10)} | {
    ".": ".",
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "Enter": "\r",
}
_NUMPAD_APPLICATION = {
    "0": f"{ESC}Op",
    "1": f"{ESC}Oq",
    "2": f"{ESC}Or",
    "3": f"{ESC}Os",
    "4": f"{ESC}Ot",
    "5": f"{ESC}Ou",
    "6": f"{ESC}Ov",
    "7": f"{ESC}Ow",
    "8": f"{ESC}Ox",
    "9": f"{ESC}Oy",
    ".": f"{ESC}On",
    "+": f"{ESC}Ok",
    "-": f"{ESC}Om",
    "*": f"{ESC}Oj",
    "/": f"{ESC}Oo",
    "Enter": f"{ESC}OM",
}


@dataclass(frozen=True)
class KeyMap:
    """How a terminal encodes its keys (and whether it encodes modifiers)."""

    function_keys: Mapping[int, str]
    cursor_keys: Mapping[str, str]  # "up"/"down"/"left"/"right" -> CSI/SS3 final byte
    nav_keys: Mapping[str, str]  # "home"/"end"/... -> CSI body
    modifiers: bool = True  # whether shift/alt/ctrl are folded into the sequence
    numpad_numeric: Mapping[str, str] = field(default_factory=lambda: _NUMPAD_NUMERIC)
    numpad_application: Mapping[str, str] = field(default_factory=lambda: _NUMPAD_APPLICATION)


def apply_modifier(sequence: str, modifier: int) -> str:
    """Fold an xterm-style modifier into a function-key sequence.

    ``ESC O X`` becomes ``ESC [ 1 ; mod X``; ``ESC [ n ~`` becomes ``ESC [ n ; mod ~``.
    """
    if sequence.startswith(f"{ESC}O") and len(sequence) == 3:
        return f"{ESC}[1;{modifier}{sequence[2]}"
    if sequence.startswith(f"{ESC}[") and sequence.endswith("~"):
        return f"{ESC}[{sequence[2:-1]};{modifier}~"
    return sequence


_ARROWS = {"up": "A", "down": "B", "right": "C", "left": "D"}

# The xterm F1-F12 repertoire, reused by screen/tmux (verified against terminfo).
_XTERM_FUNCTION_KEYS = {
    1: f"{ESC}OP",
    2: f"{ESC}OQ",
    3: f"{ESC}OR",
    4: f"{ESC}OS",
    5: f"{ESC}[15~",
    6: f"{ESC}[17~",
    7: f"{ESC}[18~",
    8: f"{ESC}[19~",
    9: f"{ESC}[20~",
    10: f"{ESC}[21~",
    11: f"{ESC}[23~",
    12: f"{ESC}[24~",
}

# The xterm editing keypad (insert/delete/page), shared by screen/tmux/rxvt.
_EDITING_KEYPAD = {"insert": "2~", "delete": "3~", "pageup": "5~", "pagedown": "6~"}

# xterm: F1-F4 as SS3 letters, F5-F12 as CSI-tilde, Home/End as H/F, modifiers encoded.
XTERM_KEYMAP = KeyMap(
    function_keys=_XTERM_FUNCTION_KEYS,
    cursor_keys=_ARROWS,
    nav_keys={"home": "H", "end": "F", **_EDITING_KEYPAD},
)

# GNU screen / tmux: xterm's function keys, but VT220-style Home/End (1~/4~). (terminfo)
SCREEN_KEYMAP = KeyMap(
    function_keys=_XTERM_FUNCTION_KEYS,
    cursor_keys=_ARROWS,
    nav_keys={"home": "1~", "end": "4~", **_EDITING_KEYPAD},
)

# rxvt-unicode: F1-F4 as CSI 11~-14~ (not SS3), Home/End as 7~/8~, no xterm modifier
# folding (rxvt uses its own shifted-key scheme). (terminfo: rxvt-unicode-256color)
URXVT_KEYMAP = KeyMap(
    function_keys={
        1: f"{ESC}[11~",
        2: f"{ESC}[12~",
        3: f"{ESC}[13~",
        4: f"{ESC}[14~",
        5: f"{ESC}[15~",
        6: f"{ESC}[17~",
        7: f"{ESC}[18~",
        8: f"{ESC}[19~",
        9: f"{ESC}[20~",
        10: f"{ESC}[21~",
        11: f"{ESC}[23~",
        12: f"{ESC}[24~",
    },
    cursor_keys=_ARROWS,
    nav_keys={"home": "7~", "end": "8~", **_EDITING_KEYPAD},
    modifiers=False,
)

# VT100: four PF keys, arrow keys, no editing keypad and no modifier encoding.
VT100_KEYMAP = KeyMap(
    function_keys={
        1: f"{ESC}OP",
        2: f"{ESC}OQ",
        3: f"{ESC}OR",
        4: f"{ESC}OS",
    },
    cursor_keys=_ARROWS,
    nav_keys={},
    modifiers=False,
)

# VT220: PF1-PF4, F6-F20 (F1-F5 are local keys), the six-key editing keypad,
# and no keyboard-modifier encoding.
VT220_KEYMAP = KeyMap(
    function_keys={
        1: f"{ESC}OP",
        2: f"{ESC}OQ",
        3: f"{ESC}OR",
        4: f"{ESC}OS",
        6: f"{ESC}[17~",
        7: f"{ESC}[18~",
        8: f"{ESC}[19~",
        9: f"{ESC}[20~",
        10: f"{ESC}[21~",
        11: f"{ESC}[23~",
        12: f"{ESC}[24~",
        13: f"{ESC}[25~",
        14: f"{ESC}[26~",
        15: f"{ESC}[28~",
        16: f"{ESC}[29~",
        17: f"{ESC}[31~",
        18: f"{ESC}[32~",
        19: f"{ESC}[33~",
        20: f"{ESC}[34~",
    },
    cursor_keys=_ARROWS,
    # The editing keypad: Find, Insert Here, Remove, Select, Prev, Next.
    nav_keys={"home": "1~", "insert": "2~", "delete": "3~", "end": "4~", "pageup": "5~", "pagedown": "6~"},
    modifiers=False,
)

# Linux console: the distinctive F1-F5 as ESC [ [ A .. E, F6-F12 as CSI-tilde.
LINUX_KEYMAP = KeyMap(
    function_keys={
        1: f"{ESC}[[A",
        2: f"{ESC}[[B",
        3: f"{ESC}[[C",
        4: f"{ESC}[[D",
        5: f"{ESC}[[E",
        6: f"{ESC}[17~",
        7: f"{ESC}[18~",
        8: f"{ESC}[19~",
        9: f"{ESC}[20~",
        10: f"{ESC}[21~",
        11: f"{ESC}[23~",
        12: f"{ESC}[24~",
    },
    cursor_keys=_ARROWS,
    nav_keys={"home": "1~", "insert": "2~", "delete": "3~", "end": "4~", "pageup": "5~", "pagedown": "6~"},
    modifiers=False,
)
