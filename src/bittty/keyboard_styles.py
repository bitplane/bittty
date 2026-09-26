"""Xterm's selectable legacy keyboards (modes 1051-1061), as KeyMaps.

Wire mappings follow xterm input.c; selection semantics follow util.c.
These are xterm compatibility modes, not full Sun/HP/SCO terminal models.
"""

from enum import Enum

from .keymap import ARROWS, CSI, DEC_EDITING, ESC, PF_KEYS, SS3, KeyMap, dec_function_keys


class KeyboardStyle(Enum):
    DEFAULT = "default"
    SUN = "sun"
    HP = "hp"
    SCO = "sco"
    LEGACY = "legacy"
    VT220 = "vt220"


_SUN_CODES = (*range(224, 234), *range(192, 202), *range(208, 223), 234, 235)
_SCO_FINALS = "MNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@[\\]^_`{"
_SS3_ARROWS = {key: SS3 + final for key, final in ARROWS.items()}
_CSI_ARROWS = {key: CSI + final for key, final in ARROWS.items()}
_DEC_KEYS = {key: CSI + body for key, body in DEC_EDITING.items()} | {"help": CSI + "28~", "menu": CSI + "29~"}
# Keys that follow DECCKM wherever a keyboard leaves them in their DEC form.
_CURSOR = {"home": "H", "end": "F", "begin": "E"}
_DEC_CURSOR = _CSI_ARROWS | {key: CSI + final for key, final in _CURSOR.items()}
_DEC_APPLICATION = _SS3_ARROWS | {key: SS3 + final for key, final in _CURSOR.items()}

STYLE_KEYMAPS = {
    KeyboardStyle.SUN: KeyMap(
        keys={
            **dec_function_keys(),
            **{f"f{n}": f"{CSI}{code}z" for n, code in enumerate(_SUN_CODES, 1)},
            **_SS3_ARROWS,
            **{
                key: f"{CSI}{code}z"
                for key, code in {
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
                }.items()
            },
            **PF_KEYS,
        },
        application={},
        delete_is_del=None,
    ),
    KeyboardStyle.HP: KeyMap(
        keys={
            **dec_function_keys(),
            **{f"f{n}": ESC + chr(ord("p") + n - 1) for n in range(1, 9)},
            **_DEC_KEYS,
            "begin": CSI + "E",
            **{
                key: ESC + final
                for key, final in {
                    **ARROWS,
                    "end": "F",
                    "clear": "J",
                    "delete": "P",
                    "insert": "Q",
                    "pagedown": "S",
                    "pageup": "T",
                    "home": "h",
                    "select": "F",
                    "find": "h",
                }.items()
            },
            **PF_KEYS,
        },
        application={"begin": SS3 + "E"},
        delete_is_del=None,
    ),
    KeyboardStyle.SCO: KeyMap(
        keys={
            **dec_function_keys(),
            **{f"f{n}": CSI + final for n, final in enumerate(_SCO_FINALS, 1)},
            **_DEC_KEYS,
            **{
                key: CSI + final
                for key, final in {**ARROWS, "begin": "E", "end": "F", "insert": "L", "pagedown": "G"}.items()
            },
            "pageup": CSI + "I",
            "home": CSI + "H",
            **PF_KEYS,
        },
        application={},
        delete_is_del=None,
    ),
    KeyboardStyle.LEGACY: KeyMap(
        keys={**dec_function_keys(), **_DEC_KEYS, **_DEC_CURSOR, **PF_KEYS},
        application=_DEC_APPLICATION,
        modifiers=False,
        ctrl_function_offset=12,
        delete_is_del=True,
    ),
    KeyboardStyle.VT220: KeyMap(
        keys={
            **dec_function_keys(),
            **{f"f{n}": SS3 + final for n, final in enumerate("PQRS", 1)},
            **_DEC_KEYS,
            **_DEC_CURSOR,
            # The VT220 has Find and Select where a PC has Home and End.
            "home": CSI + "1~",
            "end": CSI + "4~",
            **PF_KEYS,
        },
        application=_SS3_ARROWS | {"begin": SS3 + "E"},
        modifiers=False,
        ctrl_function_offset=12,
        user_keys=True,
        vt220_keypad=True,
    ),
}
