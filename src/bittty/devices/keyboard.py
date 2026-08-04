"""Keyboard input encoder for terminal key events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .. import constants
from ..keymap import apply_modifier
from ..options import DEC_KEYBOARD_LEDS, KITTY_KEYBOARD
from .modes import ModeEffect

if TYPE_CHECKING:
    from ..operations import Operation
    from .board import Board
from .base import Device

# Kitty keyboard protocol. Only the enhancements the char+modifier input API can
# express are negotiable: 1 disambiguate, 8 report-all-keys, 16 associated-text.
# Flags 2 (event types) and 4 (alternate keys) need a key-event input layer that
# does not exist, so they are ignored on push/set and therefore absent from the
# query report — feature detection tells applications the truth.
_KITTY_SUPPORTED = 0b11001
# The spec: "Terminals should limit the size of the stack as appropriate, to
# prevent Denial-of-Service attacks." Full stack evicts its oldest entry.
_KITTY_STACK_MAX = 8
# Keys that keep their legacy bytes under flag 1 so `reset` stays typeable
# after a crash; flag 8 or a beyond-shift modifier turns them into CSI u.
_KITTY_LEGACY_CODES = {"\r": 13, "\t": 9, constants.BS: 127, constants.DEL: 127}
# Keypad keys get Private Use Area functional codes under flag 8.
_KITTY_NUMPAD_CODES = {
    "0": 57399,
    "1": 57400,
    "2": 57401,
    "3": 57402,
    "4": 57403,
    "5": 57404,
    "6": 57405,
    "7": 57406,
    "8": 57407,
    "9": 57408,
    ".": 57409,
    "/": 57410,
    "*": 57411,
    "-": 57412,
    "+": 57413,
    "Enter": 57414,
}


@dataclass(slots=True)
class _KittyState:
    """Kitty flags and their push/pop stack for one screen.

    The spec: "Terminals must maintain separate stacks for the main and
    alternate screens."
    """

    flags: int = 0
    stack: list[int] = field(default_factory=list)

    def clear(self) -> None:
        self.flags = 0
        self.stack.clear()


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
        # Built directly: the blitter these key off does not exist yet.
        self._kitty = {False: _KittyState(), True: _KittyState()}
        # DECLL-loaded host indications. One set, not per-screen: LEDs are physical.
        self.led_num = False
        self.led_caps = False
        self.led_scroll = False
        self.leds_fitted = DEC_KEYBOARD_LEDS in board.model.provides
        self.handlers = {
            "DECUDK": self.set_user_keys,
            "XTMODKEYS": self.set_modify_keys,
        }
        if self.leds_fitted:
            self.handlers["DECLL"] = self.load_leds
        if KITTY_KEYBOARD in board.model.provides:
            # A terminal that does not speak the protocol does not answer its
            # negotiation at all — real xterm never replies to CSI ? u.
            self.handlers.update(
                {
                    "KITTY_PUSH": self.kitty_push,
                    "KITTY_POP": self.kitty_pop,
                    "KITTY_SET": self.kitty_set,
                    "KITTY_QUERY": self.kitty_query,
                }
            )

    @property
    def _kitty_state(self) -> _KittyState:
        return self._kitty[self.board.blitter.in_alt_screen]

    @property
    def kitty_flags(self) -> int:
        """The active screen's Kitty progressive-enhancement flags."""
        return self._kitty_state.flags

    @kitty_flags.setter
    def kitty_flags(self, value: int) -> None:
        self._kitty_state.flags = value & _KITTY_SUPPORTED

    @property
    def kitty_stack(self) -> list[int]:
        """The active screen's Kitty flag stack."""
        return self._kitty_state.stack

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
        stack = self.kitty_stack
        if len(stack) >= _KITTY_STACK_MAX:
            stack.pop(0)  # spec: evict the oldest entry rather than grow forever
        stack.append(self.kitty_flags)
        self.kitty_flags = operation.args[0]

    def kitty_pop(self, operation: Operation) -> None:
        """CSI < n u — pop n saved flag-states off the stack.

        Popping an empty stack zeroes the flags, and doing it again changes
        nothing, so one pop past the stack depth is the whole of the effect.
        """
        for _ in range(min(operation.args[0], len(self.kitty_stack) + 1)):
            self.kitty_flags = self.kitty_stack.pop() if self.kitty_stack else 0

    def kitty_set(self, operation: Operation) -> None:
        """CSI = flags ; mode u — set (1), add (2) or remove (3) flag bits."""
        flags, mode = operation.args
        if mode == 2:
            self.kitty_flags = self.kitty_flags | flags
        elif mode == 3:
            self.kitty_flags = self.kitty_flags & ~flags
        else:  # mode 1 (or default): replace
            self.kitty_flags = flags

    def kitty_query(self, operation: Operation) -> None:
        """CSI ? u — report the current Kitty flags as CSI ? flags u."""
        self.board.host.write(f"{constants.ESC}[?{self.kitty_flags}u", flush=True)

    # --- keyboard indicator LEDs (DECLL, modes 108/109/110) --- #

    def load_leds(self, operation: Operation) -> None:
        """DECLL (CSI Ps q) — load the host keyboard indications."""
        for ps in operation.args[0]:
            match ps or 0:
                case 0:
                    self.led_num = self.led_caps = self.led_scroll = False
                case 1:
                    self.led_num = True
                case 2:
                    self.led_caps = True
                case 3:
                    self.led_scroll = True
                case 21:
                    self.led_num = False
                case 22:
                    self.led_caps = False
                case 23:
                    self.led_scroll = False
        self.board.modes.reconcile(ModeEffect.KEYBOARD_INDICATOR)

    def indicator_lights(self) -> tuple[bool, bool, bool]:
        """What the keyboard LEDs display: (num, caps, scroll).

        DECKLHIM arbitrates: set, the LEDs show the DECLL-loaded host
        indications; reset, they show keyboard state (modes 108/109; Scroll
        Lock has no local state in bittty, so it is dark). A model without
        DECKLHIM in its repertoire (xterm) is host-driven unconditionally —
        its DECLL "functions" without the mode the VT510 requires.

        DECLL bits are stored even while DECKLHIM is reset: the mode selects
        what is displayed, so setting it later reveals loaded indications.
        """
        modes = self.board.modes
        if modes.get_private_mode_status(110) == 2:  # DECKLHIM known and reset
            return (modes.num_lock_mode, modes.caps_lock_mode, False)
        return (self.led_num, self.led_caps, self.led_scroll)

    @staticmethod
    def _kitty_code(char: str) -> int:
        """The unshifted codepoint: ctrl+shift+a is CSI 97, never 65.

        Non-letter shifted chars ('!') would need layout knowledge to unshift —
        flag-4 territory — so they encode as given. lower() can expand to two
        codepoints ('İ'), in which case the char also encodes as given.
        """
        lowered = char.lower()
        return ord(lowered) if len(lowered) == 1 else ord(char)

    @staticmethod
    def _kitty_sequence(code: int, modifier: int, text: str | None) -> str:
        """Build CSI code;modifiers;text u, omitting empty trailing fields."""
        if text is not None:
            codepoints = ":".join(str(ord(point)) for point in text)
            mod_field = "" if modifier == constants.KEY_MOD_NONE else str(modifier)
            return f"{constants.ESC}[{code};{mod_field};{codepoints}u"
        if modifier != constants.KEY_MOD_NONE:
            return f"{constants.ESC}[{code};{modifier}u"
        return f"{constants.ESC}[{code}u"

    def _kitty_key(self, char: str, modifier: int) -> str | None:
        """Encode one key per the active Kitty flags, or None for the legacy path.

        Flag 1 turns the Esc key and beyond-shift-modified keys into CSI u;
        plain and shift-only text keys stay text, and unmodified Enter, Tab and
        Backspace keep their legacy bytes so `reset` stays typeable. Flag 8
        encodes everything; flag 16 (meaningful only with 8) appends the text.
        """
        flags = self.kitty_flags
        if not flags or len(char) != 1:
            return None
        beyond_shift = self._modifier_bits(modifier) & ~1
        if char == constants.ESC:
            return self._kitty_sequence(27, modifier, None)
        legacy_code = _KITTY_LEGACY_CODES.get(char)
        if legacy_code is not None:
            if flags & 8 or beyond_shift:
                return self._kitty_sequence(legacy_code, modifier, None)
            return None
        if not char.isprintable():
            return None  # a bare C0 is already an encoding, not a key
        if flags & 8:
            text = char if flags & 16 else None
            return self._kitty_sequence(self._kitty_code(char), modifier, text)
        if beyond_shift:
            return self._kitty_sequence(self._kitty_code(char), modifier, None)
        return None

    def _enhanced_key(self, char: str, modifier: int) -> str | None:
        """Encode a modified character key via xterm modifyOtherKeys, else None.

        Uses CSI 27 ; mod ; code ~ with the base (unshifted) codepoint. Only
        fires when a modifier is present and Kitty (which takes precedence and
        runs earlier in input_key) is inactive.
        """
        if len(char) != 1 or modifier == constants.KEY_MOD_NONE or self.kitty_flags:
            return None
        if self.modify_other_keys >= 1:
            return f"{constants.ESC}[27;{modifier};{self._kitty_code(char)}~"
        return None

    def report_focus(self, focused: bool) -> None:
        """Focus reporting (DECSET 1004) — send CSI I on focus in, CSI O on focus out."""
        if self.board.modes.focus_reporting:
            self.board.host.write(f"{constants.ESC}[I" if focused else f"{constants.ESC}[O", flush=True)

    def reset(self, hard: bool = True) -> None:
        """RIS clears the modern-keyboard negotiation state, on both screens."""
        if hard:
            self.modify_other_keys = 0
            for state in self._kitty.values():
                state.clear()
            self.led_num = self.led_caps = self.led_scroll = False

    def _csi_key(self, body: str, modifier: int) -> str:
        """Build a CSI cursor/nav sequence, folding in a modifier if the terminal supports it."""
        keymap = self.board.model.keymap
        if modifier != constants.KEY_MOD_NONE and keymap.modifiers:
            if body.endswith("~"):  # editing-keypad keys carry the modifier as ESC[n;mod~
                return f"{constants.ESC}[{body[:-1]};{modifier}~"
            return f"{constants.ESC}[1;{modifier}{body}"
        return f"{constants.ESC}[{body}"

    @staticmethod
    def _modifier_bits(modifier: int) -> int:
        """Decode xterm's one-plus-bitmask modifier parameter."""
        return max(0, modifier - 1)

    def _special_modifier(self, modifier: int) -> tuple[int, int]:
        """Return the modifier encoded on a special key and any legacy-only bits."""
        bits = self._modifier_bits(modifier)
        if self.board.modes.special_modifiers or self.kitty_flags:
            # Under the Kitty protocol Alt/Meta live in the CSI modifier
            # parameter; an ESC prefix would be a legacy encoding.
            return modifier, 0
        legacy_bits = bits & (2 | 8)  # Alt / Meta
        return (bits & ~(2 | 8)) + 1, legacy_bits

    def _legacy_escape_prefix(self, bits: int) -> bool:
        """Whether legacy Alt/Meta policy prefixes this input with ESC."""
        modes = self.board.modes
        return bool((bits & 2 and modes.alt_sends_escape) or (bits & 8 and modes.meta_sends_escape))

    def _input_special(self, sequence: str, legacy_bits: int) -> None:
        """Send a cursor/function sequence after legacy Alt/Meta handling."""
        if self._legacy_escape_prefix(legacy_bits):
            sequence = constants.ESC + sequence
        self.input(sequence)

    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert key + modifier to standard control codes, then send to input()."""
        keymap = self.board.model.keymap

        kitty = self._kitty_key(char, modifier)
        if kitty is not None:
            self.input(kitty, local_text=char, margin_key=char.isprintable())
            return

        # Sending raw DEL for Delete recreates the ambiguity Kitty flag 1
        # removes; the named key falls through to nav_keys' CSI 3~ instead.
        if char == "delete" and self.board.modes.delete_sends_del and not self.kitty_flags:
            self.input(constants.DEL)
            return

        if char in keymap.cursor_keys:
            special_modifier, legacy_bits = self._special_modifier(modifier)
            self._input_special(self._csi_key(keymap.cursor_keys[char], special_modifier), legacy_bits)
            return

        if char in keymap.nav_keys:
            special_modifier, legacy_bits = self._special_modifier(modifier)
            self._input_special(self._csi_key(keymap.nav_keys[char], special_modifier), legacy_bits)
            return

        if char == constants.BS:
            if self.board.modes.backarrow_key_sends_bs:
                self.input(constants.BS, local_text=constants.BS)
            else:
                self.input(constants.DEL, local_text=constants.BS)
            return

        enhanced = self._enhanced_key(char, modifier)
        if enhanced is not None:  # modifyOtherKeys / Kitty encode modified keys explicitly
            self.input(enhanced, local_text=char, margin_key=char.isprintable())
            return

        # xterm modifier numbers are one plus a shift/alt/control bit mask.
        # Apply the legacy control and Alt transformations only after the
        # negotiated modern encodings above have had first refusal.
        modifier_bits = self._modifier_bits(modifier)
        control = bool(modifier_bits & 4)
        alt = bool(modifier_bits & 2)
        meta = bool(modifier_bits & 8)

        if control and len(char) == 1:
            upper_char = char.upper()
            if "A" <= upper_char <= "Z":
                char = chr(ord(upper_char) - ord("A") + 1)

        if len(char) == 1:
            local_text = char
            # Escape-prefix policy wins over the older eighth-bit Meta form.
            if (alt and self.board.modes.alt_sends_escape) or (meta and self.board.modes.meta_sends_escape):
                char = constants.ESC + char
                self.input(char, local_text=local_text, margin_key=local_text.isprintable())
            elif meta and self.board.modes.eight_bit_input and ord(char) < 128:
                self.board.transmit_keyboard_bytes(
                    bytes((ord(char) | 0x80,)),
                    local_text=local_text,
                    margin_key=local_text.isprintable(),
                )
            else:
                self.input(char, local_text=local_text, margin_key=local_text.isprintable())
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
        special_modifier, legacy_bits = self._special_modifier(modifier)
        if special_modifier != constants.KEY_MOD_NONE and keymap.modifiers:
            sequence = apply_modifier(sequence, special_modifier)
        self._input_special(sequence, legacy_bits)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to the sequence for the current keypad mode."""
        if self.kitty_flags & 8:
            code = _KITTY_NUMPAD_CODES.get(key)
            if code is not None:
                # Report-all-keys gives keypad keys their own functional codes.
                self.input(self._kitty_sequence(code, constants.KEY_MOD_NONE, None))
                return
        keymap = self.board.model.keymap
        table = keymap.numpad_numeric if self.board.modes.numeric_keypad else keymap.numpad_application
        sequence = table.get(key, key)

        local_text = key if self.board.modes.numeric_keypad and len(key) == 1 else None
        self.input(sequence, local_text=local_text, margin_key=bool(local_text and local_text.isprintable()))

    def input(self, data: str, *, local_text: str | None = None, margin_key: bool = False) -> None:
        """Translate control codes based on terminal modes and send to the host."""
        # DECCKM's SS3 forms are legacy encodings; Kitty ignores the mode.
        if self.board.modes.cursor_application_mode and not self.kitty_flags and f"{constants.ESC}[" in data:
            data = self.translate_application_cursor_keys(data)
        self.board.transmit_keyboard(data, local_text=local_text, margin_key=margin_key)

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
