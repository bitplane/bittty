"""Keyboard input encoder for terminal key events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import constants

if TYPE_CHECKING:
    from ..terminal import Terminal


class KeyboardDevice:
    """Encodes keyboard input into terminal control sequences."""

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal

    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert key + modifier to standard control codes, then send to input()."""
        if char in constants.CURSOR_KEYS:
            if modifier == constants.KEY_MOD_NONE:
                sequence = f"{constants.ESC}[{constants.CURSOR_KEYS[char]}"
            else:
                sequence = f"{constants.ESC}[1;{modifier}{constants.CURSOR_KEYS[char]}"
            self.input(sequence)
            return

        if char in constants.NAV_KEYS:
            if modifier == constants.KEY_MOD_NONE:
                sequence = f"{constants.ESC}[{constants.NAV_KEYS[char]}"
            else:
                sequence = f"{constants.ESC}[1;{modifier}{constants.NAV_KEYS[char]}"
            self.input(sequence)
            return

        if char == constants.BS:
            if self.terminal.backarrow_key_sends_bs:
                self.input(constants.BS)
            else:
                self.input(constants.DEL)
            return

        if modifier == constants.KEY_MOD_CTRL and len(char) == 1:
            upper_char = char.upper()
            if "A" <= upper_char <= "Z":
                self.input(chr(ord(upper_char) - ord("A") + 1))
                return

        if len(char) == 1 and char.isprintable():
            self.input(char)
            return

        self.input(char)

    def input_fkey(self, num: int, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert function key + modifier to standard control codes, then send to input()."""
        if 1 <= num <= 4:
            base_chars = {1: "P", 2: "Q", 3: "R", 4: "S"}
            if modifier == constants.KEY_MOD_NONE:
                sequence = f"{constants.ESC}O{base_chars[num]}"
            else:
                sequence = f"{constants.ESC}[1;{modifier}{base_chars[num]}"
        elif 5 <= num <= 12:
            codes = {5: 15, 6: 17, 7: 18, 8: 19, 9: 20, 10: 21, 11: 23, 12: 24}
            if modifier == constants.KEY_MOD_NONE:
                sequence = f"{constants.ESC}[{codes[num]}~"
            else:
                sequence = f"{constants.ESC}[{codes[num]};{modifier}~"
        else:
            return

        self.input(sequence)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to the sequence for the current keypad mode."""
        if self.terminal.numeric_keypad:
            numeric_map = {
                "0": "0",
                "1": "1",
                "2": "2",
                "3": "3",
                "4": "4",
                "5": "5",
                "6": "6",
                "7": "7",
                "8": "8",
                "9": "9",
                ".": ".",
                "+": "+",
                "-": "-",
                "*": "*",
                "/": "/",
                "Enter": "\r",
            }
            sequence = numeric_map.get(key, key)
        else:
            application_map = {
                "0": "\x1bOp",
                "1": "\x1bOq",
                "2": "\x1bOr",
                "3": "\x1bOs",
                "4": "\x1bOt",
                "5": "\x1bOu",
                "6": "\x1bOv",
                "7": "\x1bOw",
                "8": "\x1bOx",
                "9": "\x1bOy",
                ".": "\x1bOn",
                "+": "\x1bOk",
                "-": "\x1bOm",
                "*": "\x1bOj",
                "/": "\x1bOo",
                "Enter": "\x1bOM",
            }
            sequence = application_map.get(key, key)

        self.input(sequence)

    def input(self, data: str) -> None:
        """Translate control codes based on terminal modes and send to PTY."""
        if self.terminal.cursor_application_mode and f"{constants.ESC}[" in data:
            data = self.translate_application_cursor_keys(data)
        self.terminal.send(data)

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
