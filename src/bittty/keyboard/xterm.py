"""xterm's key modifier resources (XTMODKEYS) and formats (XTFMTKEYS), and the keys they govern.

Reference: xterm 407, ctlseqs and input.c.
"""

from __future__ import annotations

# The resources at their initial values: modifyKeyboard, modifyCursorKeys, modifyFunctionKeys,
# modifyKeypadKeys, modifyOtherKeys, (5, reserved), modifyModifierKeys and modifySpecialKeys.
# modifyKeyboard (the legacy/VT220 keyboards) and resources 3, 6 and 7 are stored and
# reported but change no encoding.
MODIFY_KEYS_INITIAL = (0, 2, 2, 0, 0, 0, 0, 0)
# The formats start at 0: CSI 27 ; mod ; code ~. Format 1 is CSI code ; mod u.
FORMAT_KEYS_INITIAL = (0,) * 8
MODIFY_CURSOR_KEYS, MODIFY_FUNCTION_KEYS, MODIFY_OTHER_KEYS = 1, 2, 4
_RESERVED = 5

# Named keys governed by modifyCursorKeys (the cursor and editing keypads) and
# modifyFunctionKeys (F1-F35). At level 4 they report CSI 27 ; mod ; code ~, where the
# code is the key's X keysym moved into the private-use area; Delete reports DEL.
EXTENDED_KEYS = {
    **{
        name: (MODIFY_CURSOR_KEYS, keysym - 0x1D00)
        for name, keysym in (
            ("home", 0xFF50), ("left", 0xFF51), ("up", 0xFF52), ("right", 0xFF53), ("down", 0xFF54),
            ("pageup", 0xFF55), ("pagedown", 0xFF56), ("end", 0xFF57), ("begin", 0xFF58),
            ("select", 0xFF60), ("insert", 0xFF63), ("find", 0xFF68),
        )
    },
    "delete": (MODIFY_CURSOR_KEYS, 0x7F),
    **{f"f{n}": (MODIFY_FUNCTION_KEYS, 0xFFBE + n - 1 - 0x1D00) for n in range(1, 36)},
}  # fmt: skip
# Below level 4, xterm leaves the editing keypad's modifier placement alone.
EDITING_KEYPAD = frozenset({"insert", "delete", "pageup", "pagedown", "find", "select"})


class KeyResources:
    """Eight XTMODKEYS resources (or XTFMTKEYS formats), of which a model may let the host set some."""

    def __init__(self, initial: tuple[int, ...], settable: range | tuple[int, ...]) -> None:
        self.initial = initial
        self.settable = settable
        self.values = list(initial)

    def __getitem__(self, resource: int) -> int:
        return self.values[resource]

    def set(self, params: tuple[int | None, ...]) -> None:
        """CSI > Pp ; Pv m (or f): set a resource, or restore it without Pv. A bare CSI > m restores nothing."""
        resource = params[0] if params else None
        if resource in self.settable and resource != _RESERVED:
            value = params[1] if len(params) > 1 else None
            self.values[resource] = self.initial[resource] if value is None else value

    def reset(self) -> None:
        self.values[:] = self.initial


def extended_key(code: int, modifier: int, format_: int) -> str:
    """xterm's CSI 27 ; mod ; code ~, or CSI code ; mod u when the resource's format is 1."""
    if format_:
        return f"\x1b[{code};{modifier}u"
    return f"\x1b[27;{modifier};{code}~"
