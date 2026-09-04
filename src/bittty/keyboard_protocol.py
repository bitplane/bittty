"""Kitty wire encoding shared by the keyboard device and stdio decoder.

Reference: https://sw.kovidgoyal.net/kitty/keyboard-protocol/
"""

from .keys import KeyEvent, KeyModifiers

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
ALIASES = {"\x1b": "escape", "\r": "enter", "\t": "tab", "\x08": "backspace", "\x7f": "backspace"}
_EVENT_TYPES = {"press": 1, "repeat": 2, "release": 3}


def encode_key(event: KeyEvent, flags: int) -> str | None:
    """Encode enhanced input; None selects legacy handling, empty means suppress."""
    key = ALIASES.get(event.key, event.key)
    if flags & 2 and not flags & 9 and key.startswith("kp_"):
        # Event reporting alone does not opt into distinct keypad identities.
        normal = KEYPAD_LEGACY.get(key, key[3:] if key != "kp_begin" else key)
        key = "enter" if normal == "Enter" else normal
    modifiers = int(event.modifiers)
    report_all = bool(flags & 8)
    release = event.event_type == "release"
    if release and not flags & 2:
        return ""
    functional = FUNCTIONAL.get(key)
    if functional and 57441 <= functional[0] <= 57454 and not report_all:
        return ""
    # Escape-hatch keys and ordinary text have no release reports without flag 8.
    escape_hatch = key in ("enter", "tab", "backspace")
    text_key = len(key) == 1 and not (modifiers & 62)
    if release and not report_all and (escape_hatch or text_key):
        return ""
    if not flags:
        return None
    enhanced = report_all or (flags & 1 and (key == "escape" or modifiers & 62))
    if flags & 2 and event.event_type != "press" and modifiers & 62:
        enhanced = True
    if escape_hatch and flags & 3 and modifiers & 63:
        enhanced = True
    if functional and not escape_hatch:
        enhanced = enhanced or bool(flags & 3)
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
    if flags & 4 and final == "u":
        shifted = event.shifted_key if modifiers & KeyModifiers.SHIFT else None
        base = event.base_layout_key
        if shifted is not None or base is not None:
            key_field += ":" + (str(ord(shifted)) if shifted else "")
            if base is not None:
                key_field += ":" + str(ord(base))
    mod_field = str(modifiers + 1) if modifiers else ""
    if flags & 2 and event.event_type != "press":
        mod_field = f"{modifiers + 1}:{_EVENT_TYPES[event.event_type]}"
    text = event.text if report_all and flags & 16 and not release else None
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
