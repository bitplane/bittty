"""Kitty wire encoding shared by the keyboard device and stdio decoder.

Reference: https://sw.kovidgoyal.net/kitty/keyboard-protocol/
"""

from dataclasses import dataclass, field
from enum import IntFlag

from .keys import COMMAND_MODIFIERS, KeyEvent, KeyModifiers


class KittyFlags(IntFlag):
    """The progressive enhancements a child pushes with CSI > flags u."""

    DISAMBIGUATE = 1  # escape codes for ambiguous keys, and for modified text
    REPORT_EVENTS = 2  # repeat and release events
    REPORT_ALTERNATES = 4  # shifted and base-layout keys
    REPORT_ALL_KEYS = 8  # every key as an escape code, text included
    REPORT_TEXT = 16  # the text a key produces, alongside its code


ALL_FLAGS = sum(KittyFlags)  # 31: every enhancement
_F = KittyFlags
# The spec: "Terminals should limit the size of the stack as appropriate, to
# prevent Denial-of-Service attacks." Full stack evicts its oldest entry.
_STACK_MAX = 8


@dataclass(slots=True)
class KittyStack:
    """One screen's Kitty flags and the push/pop stack behind them.

    The spec: "Terminals must maintain separate stacks for the main and
    alternate screens." Every enhancement is implemented, so any can be set.
    """

    flags: int = 0
    stack: list[int] = field(default_factory=list)

    def push(self, flags: int) -> None:
        """CSI > flags u — save the current flags and adopt new ones."""
        if len(self.stack) >= _STACK_MAX:
            self.stack.pop(0)
        self.stack.append(self.flags)
        self.flags = flags & ALL_FLAGS

    def pop(self, count: int) -> None:
        """CSI < n u — pop n saved flag-states off the stack.

        Popping an empty stack zeroes the flags, and doing it again changes
        nothing, so one pop past the stack depth is the whole of the effect.
        """
        for _ in range(min(count, len(self.stack) + 1)):
            self.flags = self.stack.pop() if self.stack else 0

    def set(self, flags: int, mode: int) -> None:
        """CSI = flags ; mode u — set (1, or default), add (2) or remove (3) flag bits."""
        if mode == 2:
            flags = self.flags | flags
        elif mode == 3:
            flags = self.flags & ~flags
        self.flags = flags & ALL_FLAGS

    def clear(self) -> None:
        self.flags = 0
        self.stack.clear()


# Canonical protocol forms. In particular F3 is 13~, never the ambiguous CPR R.
FUNCTIONAL = {
    "escape": (27, "u"),
    "enter": (13, "u"),
    "tab": (9, "u"),
    "backspace": (127, "u"),
    "insert": (2, "~"),
    "delete": (3, "~"),
    "pageup": (5, "~"),
    "pagedown": (6, "~"),
    "left": (1, "D"),
    "right": (1, "C"),
    "up": (1, "A"),
    "down": (1, "B"),
    "home": (1, "H"),
    "end": (1, "F"),
    "kp_begin": (1, "E"),
    "f1": (1, "P"),
    "f2": (1, "Q"),
    "f3": (13, "~"),
    "f4": (1, "S"),
}
FUNCTIONAL.update({f"f{i}": (code, "~") for i, code in enumerate((15, 17, 18, 19, 20, 21, 23, 24), 5)})
FUNCTIONAL.update({f"f{i}": (57363 + i, "u") for i in range(13, 36)})
FUNCTIONAL.update(
    {
        name: (57358 + i, "u")
        for i, name in enumerate(("caps_lock", "scroll_lock", "num_lock", "print_screen", "pause", "menu"))
    }
)
FUNCTIONAL.update({f"kp_{i}": (57399 + i, "u") for i in range(10)})
FUNCTIONAL.update(
    {
        f"kp_{name}": (57409 + i, "u")
        for i, name in enumerate(
            (
                "decimal",
                "divide",
                "multiply",
                "subtract",
                "add",
                "enter",
                "equal",
                "separator",
                "left",
                "right",
                "up",
                "down",
                "pageup",
                "pagedown",
                "home",
                "end",
                "insert",
                "delete",
            )
        )
    }
)
FUNCTIONAL.update(
    {
        name: (57428 + i, "u")
        for i, name in enumerate(
            (
                "media_play",
                "media_pause",
                "media_play_pause",
                "media_reverse",
                "media_stop",
                "media_fast_forward",
                "media_rewind",
                "media_track_next",
                "media_track_previous",
                "media_record",
                "lower_volume",
                "raise_volume",
                "mute_volume",
                "left_shift",
                "left_control",
                "left_alt",
                "left_super",
                "left_hyper",
                "left_meta",
                "right_shift",
                "right_control",
                "right_alt",
                "right_super",
                "right_hyper",
                "right_meta",
                "iso_level3_shift",
                "iso_level5_shift",
            )
        )
    }
)
KEYPAD_NAMES = dict(
    zip(
        "0123456789./*-+",
        [f"kp_{i}" for i in range(10)] + ["kp_decimal", "kp_divide", "kp_multiply", "kp_subtract", "kp_add"],
    )
) | {"Enter": "kp_enter"}
KEYPAD_LEGACY = {v: k for k, v in KEYPAD_NAMES.items()} | {"kp_equal": "=", "kp_separator": ","}
UNICODE_KEYS = {
    name: 57344 + i
    for i, name in enumerate(
        (
            "escape",
            "enter",
            "tab",
            "backspace",
            "insert",
            "delete",
            "left",
            "right",
            "up",
            "down",
            "pageup",
            "pagedown",
            "home",
            "end",
        )
    )
}
UNICODE_KEYS.update({f"f{i}": 57363 + i for i in range(1, 36)})
UNICODE_KEYS.update({name: code for name, (code, final) in FUNCTIONAL.items() if final == "u"})
UNICODE_KEYS["kp_begin"] = 57427
# Left Shift through right Meta: reported only when every key is.
_MODIFIER_KEYS = range(FUNCTIONAL["left_shift"][0], FUNCTIONAL["right_meta"][0] + 1)
ALIASES = {"\x1b": "escape", "\r": "enter", "\t": "tab", "\x08": "backspace", "\x7f": "backspace"}
_EVENT_TYPES = {"press": 1, "repeat": 2, "release": 3}


def encode_key(event: KeyEvent, flags: int) -> str | None:
    """Encode enhanced input; None selects legacy handling, empty means suppress."""
    key = ALIASES.get(event.key, event.key)
    if flags & _F.REPORT_EVENTS and not flags & (_F.DISAMBIGUATE | _F.REPORT_ALL_KEYS) and key.startswith("kp_"):
        # Event reporting alone does not opt into distinct keypad identities.
        normal = KEYPAD_LEGACY.get(key, key[3:] if key != "kp_begin" else key)
        key = "enter" if normal == "Enter" else normal
    modifiers = int(event.modifiers)
    report_all = bool(flags & _F.REPORT_ALL_KEYS)
    release = event.event_type == "release"
    if release and not flags & _F.REPORT_EVENTS:
        return ""
    functional = FUNCTIONAL.get(key)
    if functional and functional[0] in _MODIFIER_KEYS and not report_all:
        return ""
    # Escape-hatch keys and ordinary text have no release reports without flag 8.
    escape_hatch = key in ("enter", "tab", "backspace")
    text_key = len(key) == 1 and not (modifiers & COMMAND_MODIFIERS)
    if release and not report_all and (escape_hatch or text_key):
        return ""
    if not flags:
        return None
    enhanced = report_all or (flags & _F.DISAMBIGUATE and (key == "escape" or modifiers & COMMAND_MODIFIERS))
    if flags & _F.REPORT_EVENTS and event.event_type != "press" and modifiers & COMMAND_MODIFIERS:
        enhanced = True
    if (
        escape_hatch
        and flags & (_F.DISAMBIGUATE | _F.REPORT_EVENTS)
        and modifiers & (COMMAND_MODIFIERS | KeyModifiers.SHIFT)
    ):
        enhanced = True
    if functional and not escape_hatch:
        enhanced = enhanced or bool(flags & (_F.DISAMBIGUATE | _F.REPORT_EVENTS))
        if key.startswith("kp_") and event.text and not report_all:
            enhanced = False
    if escape_hatch and not enhanced:
        return None
    if not enhanced:
        return "" if release else None
    if functional:
        code, final = functional
    elif len(key) == 1:
        code, final = ord(key), "u"
    else:
        return ""  # this frontend's key has no protocol identity
    key_field = str(code)
    if flags & _F.REPORT_ALTERNATES and final == "u":
        shifted = event.shifted_key if modifiers & KeyModifiers.SHIFT else None
        base = event.base_layout_key
        if shifted is not None or base is not None:
            key_field += ":" + (str(ord(shifted)) if shifted else "")
            if base is not None:
                key_field += ":" + str(ord(base))
    mod_field = str(modifiers + 1) if modifiers else ""
    if flags & _F.REPORT_EVENTS and event.event_type != "press":
        mod_field = f"{modifiers + 1}:{_EVENT_TYPES[event.event_type]}"
    text = event.text if report_all and flags & _F.REPORT_TEXT and not release else None
    if text:
        final = "u"
        if functional:
            key_field = str(UNICODE_KEYS[key])
        fields = f"{key_field};{mod_field};" + ":".join(str(ord(c)) for c in text)
    elif mod_field:
        fields = f"{key_field};{mod_field}"
    else:
        fields = "" if code == 1 and final not in ("u", "~") else key_field
    return f"\x1b[{fields}{final}"
