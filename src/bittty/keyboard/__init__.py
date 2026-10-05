"""Keyboard facts and their wire encodings.

- keys: what the chrome reports — KeyEvent and KeyModifiers, with no wire format in them
- keymap: how a terminal model encodes its non-text keys, as KeyMap data
- styles: xterm's selectable legacy keyboards (modes 1050-1061), as KeyMaps
- kitty: the Kitty keyboard protocol's encoding, shared by the keyboard device and stdio
  decoder, and KittyStack, one screen's negotiated flags
- xterm: the XTMODKEYS/XTFMTKEYS resources and the extended keys they govern
- udk: DEC user-defined keys (DECUDK/DECPKA) and their memory

The keyboard *device* (bittty.devices.keyboard) is the card that uses them: it routes keys
and answers the host, while the state and its rules live here.
"""

from .keymap import KeyMap
from .keys import KeyEvent, KeyModifiers
from .styles import KeyboardStyle

__all__ = ["KeyEvent", "KeyMap", "KeyModifiers", "KeyboardStyle"]
