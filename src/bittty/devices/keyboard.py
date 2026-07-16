"""Keyboard input encoder for terminal key events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import constants
from ..keymap import apply_modifier

if TYPE_CHECKING:
    from .board import TerminalBoard
    from ..operations import Operation

# DECUDK numbers the definable keys F6-F20; map them to bittty's function-key numbers.
_DECUDK_CODE_TO_FKEY = {
    17: 6,
    18: 7,
    19: 8,
    20: 9,
    21: 10,
    23: 11,
    24: 12,
    25: 13,
    26: 14,
    28: 15,
    29: 16,
    31: 17,
    32: 18,
    33: 19,
    34: 20,
}


class KeyboardDevice:
    """Encodes keyboard input into terminal control sequences."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.user_defined_keys: dict[int, str] = {}  # DECUDK: F-number -> sequence
        self.handlers = {"DECUDK": self.set_user_keys}

    def set_user_keys(self, operation: Operation) -> None:
        """DECUDK — install user-defined strings for function keys."""
        for code, value in operation.args[0]:
            fkey = _DECUDK_CODE_TO_FKEY.get(code)
            if fkey is not None:
                self.user_defined_keys[fkey] = value

    def _csi_key(self, body: str, modifier: int) -> str:
        """Build a CSI cursor/nav sequence, folding in a modifier if the terminal supports it."""
        keymap = self.board.personality.keymap
        if modifier != constants.KEY_MOD_NONE and keymap.modifiers:
            return f"{constants.ESC}[1;{modifier}{body}"
        return f"{constants.ESC}[{body}"

    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert key + modifier to standard control codes, then send to input()."""
        keymap = self.board.personality.keymap

        if char in keymap.cursor_keys:
            self.input(self._csi_key(keymap.cursor_keys[char], modifier))
            return

        if char in keymap.nav_keys:
            self.input(self._csi_key(keymap.nav_keys[char], modifier))
            return

        if char == constants.BS:
            if self.board.modes.backarrow_key_sends_bs:
                self.input(constants.BS)
            else:
                self.input(constants.DEL)
            return

        if modifier == constants.KEY_MOD_CTRL and len(char) == 1:
            upper_char = char.upper()
            if "A" <= upper_char <= "Z":
                self.input(chr(ord(upper_char) - ord("A") + 1))
                return

        if len(char) == 1:
            # A single character (printable or control) is sent as-is.
            self.input(char)
        # A multi-character key name this terminal's keymap does not define is ignored.

    def input_fkey(self, num: int, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Encode a function key using any user-defined string, else the keymap."""
        if num in self.user_defined_keys:
            self.input(self.user_defined_keys[num])
            return
        keymap = self.board.personality.keymap
        sequence = keymap.function_keys.get(num)
        if sequence is None:
            return  # this terminal has no such function key
        if modifier != constants.KEY_MOD_NONE and keymap.modifiers:
            sequence = apply_modifier(sequence, modifier)
        self.input(sequence)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to the sequence for the current keypad mode."""
        keymap = self.board.personality.keymap
        table = keymap.numpad_numeric if self.board.modes.numeric_keypad else keymap.numpad_application
        sequence = table.get(key, key)

        self.input(sequence)

    def input(self, data: str) -> None:
        """Translate control codes based on terminal modes and send to the host."""
        if self.board.modes.cursor_application_mode and f"{constants.ESC}[" in data:
            data = self.translate_application_cursor_keys(data)
        self.board.host.write(data)

    def translate_application_cursor_keys(self, data: str) -> str:
        """Translate embedded normal cursor-key CSI sequences to application mode."""
        result = []
        index = 0
        while index < len(data):
            if (
                data[index] == constants.ESC
                and index + 2 < len(data)
                and data[index + 1] == "["
                and data[index + 2] in "ABCD"
            ):
                result.append(f"{constants.ESC}O{data[index + 2]}")
                index += 3
            else:
                result.append(data[index])
                index += 1
        return "".join(result)
