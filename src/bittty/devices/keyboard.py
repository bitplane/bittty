"""Keyboard input encoder for terminal key events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import constants
from ..keymap import apply_modifier

if TYPE_CHECKING:
    from .board import Board
    from ..operations import Operation
from .base import Device

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


class KeyboardDevice(Device):
    """Encodes keyboard input into terminal control sequences."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.user_defined_keys: dict[int, str] = {}  # DECUDK: F-number -> sequence
        self.modify_other_keys = 0  # xterm modifyOtherKeys level (0/1/2)
        self.kitty_flags = 0  # Kitty keyboard progressive-enhancement flags
        self.kitty_stack: list[int] = []  # Kitty flag stack (push/pop)
        self.handlers = {
            "DECUDK": self.set_user_keys,
            "XTMODKEYS": self.set_modify_keys,
            "KITTY_PUSH": self.kitty_push,
            "KITTY_POP": self.kitty_pop,
            "KITTY_SET": self.kitty_set,
            "KITTY_QUERY": self.kitty_query,
        }

    def set_user_keys(self, operation: Operation) -> None:
        """DECUDK — install user-defined strings for function keys."""
        for code, value in operation.args[0]:
            fkey = _DECUDK_CODE_TO_FKEY.get(code)
            if fkey is not None:
                self.user_defined_keys[fkey] = value

    # --- modern keyboard negotiation (xterm modifyOtherKeys, Kitty protocol) --- #

    def set_modify_keys(self, operation: Operation) -> None:
        """XTMODKEYS (CSI > Pp ; Pv m) — set a key-modifier resource; Pp 4 is modifyOtherKeys."""
        params = operation.args[0]
        resource = params[0] if params and params[0] is not None else 0
        value = params[1] if len(params) > 1 and params[1] is not None else 0
        if resource == 4:
            self.modify_other_keys = value

    def kitty_push(self, operation: Operation) -> None:
        """CSI > flags u — save the current flags and adopt new ones."""
        self.kitty_stack.append(self.kitty_flags)
        self.kitty_flags = operation.args[0] & 0b11111

    def kitty_pop(self, operation: Operation) -> None:
        """CSI < n u — pop n saved flag-states off the stack."""
        for _ in range(operation.args[0]):
            self.kitty_flags = self.kitty_stack.pop() if self.kitty_stack else 0

    def kitty_set(self, operation: Operation) -> None:
        """CSI = flags ; mode u — set (1), add (2) or remove (3) flag bits."""
        flags, mode = operation.args
        flags &= 0b11111
        if mode == 2:
            self.kitty_flags |= flags
        elif mode == 3:
            self.kitty_flags &= ~flags
        else:  # mode 1 (or default): replace
            self.kitty_flags = flags

    def kitty_query(self, operation: Operation) -> None:
        """CSI ? u — report the current Kitty flags as CSI ? flags u."""
        self.board.host.write(f"{constants.ESC}[?{self.kitty_flags}u", flush=True)

    def _enhanced_key(self, char: str, modifier: int) -> str | None:
        """Encode a modified character key via the active modern protocol, else None.

        Kitty takes precedence and uses the CSI-u form (CSI code ; mod u); xterm
        modifyOtherKeys uses CSI 27 ; mod ; code ~. The key code is the base
        (unshifted) codepoint. Only fires when a modifier is actually present.
        """
        if len(char) != 1 or modifier == constants.KEY_MOD_NONE:
            return None
        code = ord(char.lower())
        if self.kitty_flags:
            return f"{constants.ESC}[{code};{modifier}u"
        if self.modify_other_keys >= 1:
            return f"{constants.ESC}[27;{modifier};{code}~"
        return None

    def report_focus(self, focused: bool) -> None:
        """Focus reporting (DECSET 1004) — send CSI I on focus in, CSI O on focus out."""
        if self.board.modes.focus_reporting:
            self.board.host.write(f"{constants.ESC}[I" if focused else f"{constants.ESC}[O", flush=True)

    def reset(self, hard: bool = True) -> None:
        """RIS clears the modern-keyboard negotiation state."""
        if hard:
            self.modify_other_keys = 0
            self.kitty_flags = 0
            self.kitty_stack = []

    def _csi_key(self, body: str, modifier: int) -> str:
        """Build a CSI cursor/nav sequence, folding in a modifier if the terminal supports it."""
        keymap = self.board.model.keymap
        if modifier != constants.KEY_MOD_NONE and keymap.modifiers:
            if body.endswith("~"):  # editing-keypad keys carry the modifier as ESC[n;mod~
                return f"{constants.ESC}[{body[:-1]};{modifier}~"
            return f"{constants.ESC}[1;{modifier}{body}"
        return f"{constants.ESC}[{body}"

    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert key + modifier to standard control codes, then send to input()."""
        keymap = self.board.model.keymap

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

        enhanced = self._enhanced_key(char, modifier)
        if enhanced is not None:  # modifyOtherKeys / Kitty encode modified keys explicitly
            self.input(enhanced)
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
        keymap = self.board.model.keymap
        sequence = keymap.function_keys.get(num)
        if sequence is None:
            return  # this terminal has no such function key
        if modifier != constants.KEY_MOD_NONE and keymap.modifiers:
            sequence = apply_modifier(sequence, modifier)
        self.input(sequence)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to the sequence for the current keypad mode."""
        keymap = self.board.model.keymap
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
