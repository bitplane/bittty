"""Keyboard encoding as data.

Real terminals diverge most in their non-text keys: a VT100 has only PF1-PF4 and no
modifier encoding, while xterm sends F1-F63 and folds shift/alt/ctrl into a ``;mod``
parameter. A `KeyMap` captures those differences as data. Model keymaps and xterm's
selectable keyboards (see styles) are both KeyMaps, and the keyboard device
has a single encoder for them.

Keys are named as in `KeyEvent`: ``up``, ``home``, ``f13``, plus ``pf1``-``pf4`` for
the DEC keypad function keys and ``backtab`` for Shift-Tab (terminfo kcbt). Keypad tables use the keypad's legends: ``0``-``9``,
``.``, ``Enter`` and so on.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping

ESC = "\x1b"
CSI = ESC + "["
SS3 = ESC + "O"

ARROWS = {"up": "A", "down": "B", "right": "C", "left": "D"}
# The DEC keypad function keys PF1-PF4. Their modifiers stay inside the SS3 sequence.
PF_KEYS = {f"pf{n}": SS3 + final for n, final in enumerate("PQRS", 1)}
# F1-F4 sent as PF1-PF4 (xterm, the VT100's four keys, the VT220's local keys).
SS3_FUNCTION_KEYS = {f"f{n}": PF_KEYS[f"pf{n}"] for n in range(1, 5)}

# The numeric and application keypad, standard across the terminals modelled here.
KEYPAD_NUMERIC = {str(d): str(d) for d in range(10)} | {
    ".": ".",
    "+": "+",
    "-": "-",
    "*": "*",
    "/": "/",
    "=": "=",
    ",": ",",
    "Enter": "\r",
    "Tab": "\t",
    "Space": " ",
}
KEYPAD_APPLICATION = {str(d): SS3 + final for d, final in enumerate("pqrstuvwxy")} | {
    ".": SS3 + "n",
    "+": SS3 + "k",
    "-": SS3 + "m",
    "*": SS3 + "j",
    "/": SS3 + "o",
    "=": SS3 + "X",
    ",": SS3 + "l",
    "Enter": SS3 + "M",
    "Tab": SS3 + "I",
    "Space": SS3 + " ",
}
# The editing keys printed on a PC keypad, by the keypad key they share.
KEYPAD_POSITIONS = {
    "insert": "0",
    "end": "1",
    "down": "2",
    "pagedown": "3",
    "left": "4",
    "begin": "5",
    "right": "6",
    "home": "7",
    "up": "8",
    "pageup": "9",
    "delete": ".",
}


def arrows(prefix: str) -> dict[str, str]:
    return {key: prefix + final for key, final in ARROWS.items()}


@dataclass(frozen=True)
class KeyMap:
    """How a terminal encodes its keys (and whether it encodes modifiers)."""

    keys: Mapping[str, str]  # key name -> sequence
    # DECCKM replacements; the SS3 cursor keys by default.
    application: Mapping[str, str] = field(default_factory=lambda: arrows(SS3))
    modified: Mapping[str, str] = field(default_factory=dict)  # replacements when modifiers are folded in
    modifiers: bool = True  # whether shift/alt/ctrl are folded into the sequence
    modifiers_with_other_keys: bool = False  # ...or only once modifyOtherKeys is set (xterm legacy/VT220)
    keypad_modifiers: bool = True  # whether keypad keys (PF1-PF4, DECKPAM) carry them too
    keypad: Mapping[str, str] = field(default_factory=lambda: KEYPAD_APPLICATION)  # DECKPAM
    numeric: Mapping[str, str] = field(default_factory=lambda: KEYPAD_NUMERIC)  # DECKPNM
    ctrl_function_offset: int = 0  # xterm ctrlFKeys: Ctrl-Fn sends F(n + offset), unmodified
    user_keys: bool = False  # Shift-F6-F20 send DECUDK strings when defined
    # Delete sends DEL: False honours mode 1037, True also defaults to DEL, None never.
    delete_is_del: bool | None = False
    delete_unmodified: bool = False  # the editing-keypad Delete ignores modifiers (xterm Sun keys)
    # The VT220 keypad: ',' where a PC has '+', Ctrl-',' is '-', and the keypad's
    # editing legends send keypad codes.
    vt220_keypad: bool = False
    keypad_meta_prefix: bool = False  # Alt/Meta ESC-prefix keypad keys too (tmux)


def apply_modifier(sequence: str, modifier: int, *, keypad: bool = False, placement: int = 2) -> str:
    """Fold an xterm modifier parameter into a key sequence.

    ``placement`` is xterm's modifyCursorKeys/modifyFunctionKeys level. At the
    default, 2, ``ESC O X`` becomes ``ESC [ 1 ; mod X``, ``ESC [ n ~`` becomes
    ``ESC [ n ; mod ~`` and a bare ``ESC X`` becomes ``ESC [ 1 ; mod X``; 3 marks
    that ``ESC [ >``. Level 0 puts a lone modifier first, keeping the prefix
    (``ESC O mod X``); 1 does so behind CSI. Keypad keys keep their SS3 form,
    ``ESC O mod X``, as in xterm.
    """
    if modifier <= 1:
        return sequence
    prefix = sequence[:2] if sequence.startswith((CSI, SS3)) else ESC
    params = sequence[len(prefix) : -1]
    if not keypad and placement:
        prefix = CSI + ">" if placement == 3 else CSI
        params = params or ("1" if placement > 1 else "")
    return f"{prefix}{params + ';' if params else ''}{modifier}{sequence[-1]}"


def vt52_keymap(keymap: KeyMap) -> KeyMap:
    """What a keymap sends in VT52 mode (xterm 407): ESC-letter cursor keys, F1-F4 and PF1-PF4
    as ESC P-S, ESC ? keypad codes, and no modifiers; its other keys are unchanged.
    """
    keys = {key: ESC + final for key, final in ARROWS.items()} | {"home": ESC + "H", "end": ESC + "F"}
    keys |= {f"{bank}{n}": ESC + final for bank in ("f", "pf") for n, final in enumerate("PQRS", 1)}
    return replace(
        keymap,
        keys={**keymap.keys, **keys},
        application=keys,
        modified={},
        modifiers=False,
        modifiers_with_other_keys=False,
        keypad_modifiers=False,
        keypad={key: ESC + "?" + sequence[len(SS3) :] for key, sequence in keymap.keypad.items()},
    )


# The VT220 function-key codes for F1-F20; xterm continues from F21 as n + 21.
DEC_FUNCTION_CODES = (11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26, 28, 29, 31, 32, 33, 34)
DEC_EDITING = {"find": "1~", "insert": "2~", "delete": "3~", "select": "4~", "pageup": "5~", "pagedown": "6~"}
# The VT220's editing keypad, Help and Do (which xterm calls menu).
DEC_KEYS = {key: CSI + body for key, body in DEC_EDITING.items()} | {"help": CSI + "28~", "menu": CSI + "29~"}


def dec_function_keys(first: int = 1, last: int = 63) -> dict[str, str]:
    """CSI n ~ function keys, numbered as on the VT220 and continued by xterm."""
    return {f"f{n}": f"{CSI}{DEC_FUNCTION_CODES[n - 1] if n <= 20 else n + 21}~" for n in range(first, last + 1)}


# xterm's default keyboard: F1-F4 as SS3, the rest CSI-tilde; Home/End/Begin follow DECCKM.
# (xterm input.c; checked against xterm 407)
XTERM_KEYMAP = KeyMap(
    keys={
        **arrows(CSI),
        "home": CSI + "H",
        "end": CSI + "F",
        "begin": CSI + "E",
        **DEC_KEYS,
        "backtab": CSI + "Z",
        **PF_KEYS,
        **SS3_FUNCTION_KEYS,
        **dec_function_keys(5),
    },
    application={**arrows(SS3), "home": SS3 + "H", "end": SS3 + "F", "begin": SS3 + "E"},
)

# bittty: xterm's keyboard, plus DECUDK strings on Shift-F6-F20 without selecting the VT220 keyboard.
BITTTY_KEYMAP = replace(XTERM_KEYMAP, user_keys=True)

# The xterm F1-F12 repertoire, reused by screen/tmux (verified against terminfo).
_XTERM_FUNCTION_KEYS = SS3_FUNCTION_KEYS | dec_function_keys(5, 12)
# The xterm editing keypad (insert/delete/page), shared by screen/tmux/rxvt.
_EDITING_KEYPAD = {key: CSI + DEC_EDITING[key] for key in ("insert", "delete", "pageup", "pagedown")}

# GNU screen / tmux: xterm's function keys, but VT220-style Home/End (1~/4~) (terminfo),
# and keypad keys without modifier parameters (tmux 3.6: Shift-KP0 in DECKPAM is ESC O p).
SCREEN_KEYMAP = KeyMap(
    keys={
        **_XTERM_FUNCTION_KEYS,
        **arrows(CSI),
        "home": CSI + "1~",
        "end": CSI + "4~",
        **_EDITING_KEYPAD,
        "backtab": CSI + "Z",
    },
    keypad_modifiers=False,
)

# tmux 3.6 (checked with send-keys): screen's keys, but modified Home/End take the xterm
# CSI 1;m H/F forms, Alt/Meta is always an ESC prefix on keypad keys as well as text, and the
# numeric keypad's Enter is LF.
TMUX_KEYMAP = replace(
    SCREEN_KEYMAP,
    modified={"home": CSI + "H", "end": CSI + "F"},
    keypad_meta_prefix=True,
    numeric={**KEYPAD_NUMERIC, "Enter": "\n"},
)

# rxvt-unicode: F1-F4 as CSI 11~-14~ (not SS3), Home/End as 7~/8~, no xterm modifier
# folding (rxvt uses its own shifted-key scheme). (terminfo: rxvt-unicode-256color)
URXVT_KEYMAP = KeyMap(
    keys={
        **dec_function_keys(1, 12),
        **arrows(CSI),
        "home": CSI + "7~",
        "end": CSI + "8~",
        **_EDITING_KEYPAD,
        "backtab": CSI + "Z",
    },
    modifiers=False,
)

# VT100: four PF keys, arrow keys, no editing keypad and no modifier encoding.
VT100_KEYMAP = KeyMap(
    keys={**PF_KEYS, **SS3_FUNCTION_KEYS, **arrows(CSI)},
    modifiers=False,
)

# VT220: PF1-PF4, F6-F20 (F1-F5 are local keys; F15 is Help and F16 is Do), the six-key
# editing keypad (Find, Insert Here, Remove, Select, Prev, Next), and no modifier encoding.
VT220_KEYMAP = KeyMap(
    keys={
        **PF_KEYS,
        **SS3_FUNCTION_KEYS,
        **dec_function_keys(6, 20),
        **arrows(CSI),
        **DEC_KEYS,
        "home": CSI + "1~",
        "end": CSI + "4~",
    },
    modifiers=False,
    user_keys=True,
)

# Linux console: the distinctive F1-F5 as ESC [ [ A .. E, F6-F12 as CSI-tilde.
LINUX_KEYMAP = KeyMap(
    keys={
        **{f"f{n}": CSI + "[" + final for n, final in enumerate("ABCDE", 1)},
        **dec_function_keys(6, 12),
        **arrows(CSI),
        "home": CSI + "1~",
        "insert": CSI + "2~",
        "delete": CSI + "3~",
        "end": CSI + "4~",
        "pageup": CSI + "5~",
        "pagedown": CSI + "6~",
        "backtab": ESC + "\t",
    },
    modifiers=False,
)
