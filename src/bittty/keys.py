"""Frontend key facts, independent of terminal models and wire encodings."""

from dataclasses import dataclass
from enum import IntFlag
from typing import Literal


class KeyModifiers(IntFlag):
    NONE = 0
    SHIFT = 1
    ALT = 2
    CTRL = 4
    SUPER = 8
    HYPER = 16
    META = 32
    CAPS_LOCK = 64
    NUM_LOCK = 128


@dataclass(frozen=True, slots=True)
class KeyEvent:
    """An unshifted character or named key and facts supplied by the frontend.

    Names use lower case: ``up``, ``f1``, ``kp_0``, ``left_shift``. ``text``
    is the produced text, not a character inferred from the key or layout.
    Unknown text/alternate identities stay None. Layouts and hardware adapters
    translate their native identities here; the board never guesses a layout.
    Modifiers describe state *after* this event, including modifier releases.
    """

    key: str
    modifiers: KeyModifiers = KeyModifiers.NONE
    event_type: Literal["press", "repeat", "release"] = "press"
    text: str | None = None
    shifted_key: str | None = None
    base_layout_key: str | None = None

    def __post_init__(self):
        if not self.key or any(0xD800 <= ord(c) <= 0xDFFF for c in self.key):
            raise ValueError("key must be a character or nonempty key name")
        if self.event_type not in ("press", "repeat", "release"):
            raise ValueError("invalid key event type")
        if int(self.modifiers) < 0 or int(self.modifiers) & ~255:
            raise ValueError("invalid key modifiers")
        for alternate in (self.shifted_key, self.base_layout_key):
            if alternate is not None and (len(alternate) != 1 or not valid_text(alternate)):
                raise ValueError("alternate keys must be Unicode text characters")
        if self.text is not None and not valid_text(self.text):
            raise ValueError("key text must not contain controls or surrogates")


def valid_text(text: str) -> bool:
    return all(ord(c) >= 32 and not 127 <= ord(c) <= 159 and not 0xD800 <= ord(c) <= 0xDFFF for c in text)


def legacy_modifiers(modifier: int) -> KeyModifiers:
    """Adapt the old one-plus-mask API, whose bit 8 meant Meta, not Super."""
    bits = max(0, modifier - 1)
    return KeyModifiers((bits & 7) | (32 if bits & 8 else 0))
