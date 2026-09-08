"""Xterm's selectable legacy keyboard encodings, independent of physical layouts.

Wire mappings follow xterm input.c; selection semantics follow util.c.
These are xterm compatibility modes, not full Sun/HP/SCO terminal models.
"""

from enum import Enum


class KeyboardStyle(Enum):
    DEFAULT = "default"
    SUN = "sun"
    HP = "hp"
    SCO = "sco"
    LEGACY = "legacy"
    VT220 = "vt220"


_DEC_CODES = (11, 12, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26, 28, 29, 31, 32, 33, 34)
_SUN_CODES = (*range(224, 234), *range(192, 202), *range(208, 223), 234, 235)
_SCO_FINALS = "MNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@[\\]^_`{"
_ARROWS = {"up": "A", "down": "B", "right": "C", "left": "D"}
_DEC_EDIT = {"find": "1~", "insert": "2~", "delete": "3~", "select": "4~", "pageup": "5~", "pagedown": "6~"}
_HP_KEYS = {
    **_ARROWS,
    "end": "F",
    "clear": "J",
    "delete": "P",
    "insert": "Q",
    "pagedown": "S",
    "pageup": "T",
    "home": "h",
    "select": "F",
    "find": "h",
}
_SCO_KEYS = {**_ARROWS, "begin": "E", "end": "F", "insert": "L", "pagedown": "G", "pageup": "I", "home": "H"}
_SUN_KEYS = {
    "help": 196,
    "menu": 197,
    "find": 1,
    "insert": 2,
    "delete": 3,
    "select": 4,
    "pageup": 216,
    "pagedown": 222,
    "home": 214,
    "end": 220,
    "begin": 218,
}
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


def function_sequence(style: KeyboardStyle, number: int) -> str | None:
    if number < 1 or number > 63:
        return None
    if style is KeyboardStyle.SUN and number <= len(_SUN_CODES):
        return f"\x1b[{_SUN_CODES[number - 1]}z"
    if style is KeyboardStyle.HP and number <= 8:
        return "\x1b" + chr(ord("p") + number - 1)
    if style is KeyboardStyle.SCO and number <= len(_SCO_FINALS):
        return "\x1b[" + _SCO_FINALS[number - 1]
    if number <= 4 and style is not KeyboardStyle.LEGACY:
        return "\x1bO" + "PQRS"[number - 1]
    code = _DEC_CODES[number - 1] if number <= 20 else number + 21
    return f"\x1b[{code}~"


def special_sequence(style: KeyboardStyle, key: str, application_cursor: bool) -> str | None:
    if style is KeyboardStyle.HP and key in _HP_KEYS:
        return "\x1b" + _HP_KEYS[key]
    if style is KeyboardStyle.SCO and key in _SCO_KEYS:
        return "\x1b[" + _SCO_KEYS[key]
    if style is KeyboardStyle.SUN:
        if key in _SUN_KEYS:
            return f"\x1b[{_SUN_KEYS[key]}z"
        if key in _ARROWS:
            return "\x1bO" + _ARROWS[key]
    if style is KeyboardStyle.VT220:
        key = {"home": "find", "end": "select"}.get(key, key)
    if key in _DEC_EDIT:
        return "\x1b[" + _DEC_EDIT[key]
    if key in ("help", "menu"):
        return "\x1b[28~" if key == "help" else "\x1b[29~"
    final = _ARROWS.get(key) or {"home": "H", "end": "F", "begin": "E"}.get(key)
    if final:
        return ("\x1bO" if application_cursor else "\x1b[") + final
    return None


def modify_sequence(sequence: str, modifier: int, mode: int = 2) -> str:
    """Xterm modifier placement: original, CSI, second parameter, private CSI."""
    if modifier <= 1 or mode < 0:
        return sequence
    prefix = sequence[:2] if sequence.startswith(("\x1b[", "\x1bO")) else "\x1b"
    params = sequence[len(prefix) : -1]
    if mode >= 1:
        prefix = "\x1b["
    if not params and mode >= 2:
        params = "1"
    if mode == 3:
        prefix += ">"
    return f"{prefix}{params + ';' if params else ''}{modifier}{sequence[-1]}"
