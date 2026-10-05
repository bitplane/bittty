"""DEC user-defined keys (DECUDK): strings on Shift-F6-F20, in a fixed memory, behind a lock."""

from __future__ import annotations

from .keymap import DEC_FUNCTION_CODES

# DECUDK numbers the definable keys F6-F20 by their VT220 codes.
_CODE_TO_FKEY = {code: n for n, code in enumerate(DEC_FUNCTION_CODES, 1) if n >= 6}


class UserKeys:
    """The downloaded strings by function-key number, and the lock that keeps them."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity  # bytes of key memory
        self.keys: dict[int, bytes] = {}
        self.locked = False  # the download lock: DECUDK cannot unlock it, Set-Up can

    @property
    def free(self) -> int:
        return self.capacity - sum(map(len, self.keys.values()))

    def load(self, clear: int, lock: int, definitions: list[tuple[int, bytes]]) -> None:
        """DECUDK — clear all first (0) or only the keys redefined; lock afterwards (0) or not."""
        if self.locked:
            return
        if clear == 0:
            self.keys.clear()
        for code, value in definitions:
            fkey = _CODE_TO_FKEY.get(code)
            if fkey is not None:
                self.keys.pop(fkey, None)
                if value and len(value) <= self.free:
                    self.keys[fkey] = value
        self.locked = lock == 0

    def program(self, action: int) -> None:
        """DECPKA — 1 locks the keys; 2 (factory defaults) and 3 (the saved definitions: bittty
        has no Set-Up to save any) clear them, unless they are locked."""
        if action == 1:
            self.locked = True
        elif action in (2, 3) and not self.locked:
            self.keys.clear()

    def reset(self) -> None:
        self.keys.clear()
        self.locked = False
