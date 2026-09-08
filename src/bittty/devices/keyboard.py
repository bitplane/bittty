"""Keyboard input encoder for terminal key events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .. import constants
from ..keyboard_protocol import ALIASES, KEYPAD_LEGACY, KEYPAD_NAMES, encode_key
from ..keyboard_styles import KEYPAD_POSITIONS, KeyboardStyle, function_sequence, modify_sequence, special_sequence
from ..keymap import apply_modifier
from ..keys import KeyEvent, KeyModifiers, legacy_modifiers, valid_text
from ..options import DEC_KEYBOARD_LEDS, DEC_USER_KEYS, KITTY_KEYBOARD
from .modes import ModeEffect

if TYPE_CHECKING:
    from ..operations import Operation
    from .board import Board
from .base import Device

# All five enhancements are implemented by the explicit key-event encoder.
_KITTY_SUPPORTED = 31
# The spec: "Terminals should limit the size of the stack as appropriate, to
# prevent Denial-of-Service attacks." Full stack evicts its oldest entry.
_KITTY_STACK_MAX = 8
_CONTROL_TEXT = dict(zip(" @2345678?[/\\]^_~", (0, 0, 0, 27, 28, 29, 30, 31, 127, 127, 27, 31, 28, 29, 30, 31, 30)))


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
        self.user_defined_keys: dict[int, bytes] = {}  # DECUDK: F-number -> wire bytes
        self.user_keys_locked = False
        self.style = KeyboardStyle.DEFAULT
        self.saved_style = KeyboardStyle.DEFAULT
        self.delete_policy_explicit = False
        self.saved_delete = (False, False)
        self.modify_other_keys = 0  # xterm modifyOtherKeys level (0/1/2)
        self.paste_bracketed = False
        # Built directly: the blitter these key off does not exist yet.
        self._kitty = {False: _KittyState(), True: _KittyState()}
        # DECLL-loaded host indications. One set, not per-screen: LEDs are physical.
        self.led_num = False
        self.led_caps = False
        self.led_scroll = False
        self.leds_fitted = DEC_KEYBOARD_LEDS in board.model.provides
        self.handlers = {
            "XTMODKEYS": self.set_modify_keys,
        }
        if DEC_USER_KEYS in board.model.provides:
            self.handlers["DECUDK"] = self.set_user_keys
            self.handlers["DSR_USER_KEYS"] = self.report_user_keys
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
        if self.user_keys_locked:
            return
        clear, lock, definitions = operation.args
        if clear == 0:
            self.user_defined_keys.clear()
        used = sum(map(len, self.user_defined_keys.values()))
        for code, value in definitions:
            fkey = _DECUDK_CODE_TO_FKEY.get(code)
            if fkey is not None:
                used -= len(self.user_defined_keys.pop(fkey, b""))
                if value and used + len(value) <= self.board.model.udk_capacity:
                    self.user_defined_keys[fkey] = value
                    used += len(value)
        self.user_keys_locked = lock == 0

    def report_user_keys(self, operation: Operation) -> None:
        """DSR 25 reports the download lock, not the keyboard action lock."""
        self.board.host.write(f"\x1b[?{21 if self.user_keys_locked else 20}n", flush=True)

    def set_user_keys_locked(self, locked: bool) -> None:
        """Operator Set-Up control; DECUDK cannot unlock downloaded keys."""
        self.user_keys_locked = locked

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
            # Xterm keyboard selection survives RIS, unlike its saved slot.
            self.saved_style = KeyboardStyle.DEFAULT
            self.delete_policy_explicit = False
            self.saved_delete = (False, False)
            self.user_defined_keys.clear()
            self.user_keys_locked = False
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
        if self.kitty_flags:
            key = chr(self._kitty_code(char)) if len(char) == 1 and char not in ALIASES else char
            self.input_key_event(
                KeyEvent(key, legacy_modifiers(modifier), text=char if len(char) == 1 and valid_text(char) else None)
            )
            return
        self._legacy_key(char, modifier)

    def _legacy_key(self, char: str, modifier: int) -> None:
        if char == "escape":
            char = constants.ESC
        keymap = self.board.model.keymap

        if self.style is not KeyboardStyle.DEFAULT and len(char) > 1 and self._style_key(char, modifier):
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

        if char == constants.ESC:
            if self.board.modes.application_escape:
                self.input("\x1bO[")
                return
            char = "\x1c" if self.board.modes.escape_sends_fs else constants.ESC

        # xterm modifier numbers are one plus a shift/alt/control bit mask.
        # Apply the legacy control and Alt transformations only after the
        # negotiated modern encodings above have had first refusal.
        modifier_bits = self._modifier_bits(modifier)
        control = bool(modifier_bits & 4)
        alt = bool(modifier_bits & 2)
        meta = bool(modifier_bits & 8)

        if control and len(char) == 1:
            upper_char = char.upper()
            if len(upper_char) == 1 and "A" <= upper_char <= "Z":
                char = chr(ord(upper_char) - ord("A") + 1)
            elif char in _CONTROL_TEXT:
                char = chr(_CONTROL_TEXT[char])

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
        if self.kitty_flags:
            self.input_key_event(KeyEvent(f"f{num}", legacy_modifiers(modifier)))
            return
        self._legacy_fkey(num, modifier)

    def _legacy_fkey(self, num: int, modifier: int) -> None:
        if self.style is not KeyboardStyle.DEFAULT:
            self._style_fkey(num, modifier)
            return
        if modifier == constants.KEY_MOD_SHIFT and num in self.user_defined_keys:
            self.board.transmit_keyboard_bytes(self.user_defined_keys[num])
            return
        keymap = self.board.model.keymap
        sequence = keymap.function_keys.get(num)
        if sequence is None:
            return  # this terminal has no such function key
        special_modifier, legacy_bits = self._special_modifier(modifier)
        if special_modifier != constants.KEY_MOD_NONE and keymap.modifiers:
            sequence = apply_modifier(sequence, special_modifier)
        self._input_special(sequence, legacy_bits)

    def _style_send(self, sequence: str, modifier: int) -> None:
        if self.style in (KeyboardStyle.LEGACY, KeyboardStyle.VT220):
            modifier, legacy_bits = 1, 0
        else:
            modifier, legacy_bits = self._special_modifier(modifier)
        sequence = modify_sequence(sequence, modifier)
        if self._legacy_escape_prefix(legacy_bits):
            sequence = constants.ESC + sequence
        # Already encoded: DECCKM must not rewrite SCO cursor codes.
        self.board.transmit_keyboard(sequence)

    def _style_key(self, key: str, modifier: int) -> bool:
        modes = self.board.modes
        if key == "delete" and self.style in (KeyboardStyle.LEGACY, KeyboardStyle.VT220):
            legacy_default = self.style is KeyboardStyle.LEGACY and not self.delete_policy_explicit
            if modes.delete_sends_del or legacy_default:
                self.board.transmit_keyboard(constants.DEL)
                return True
        if key.startswith("pf") and key[2:] in ("1", "2", "3", "4"):
            self._style_keypad_send("\x1bO" + "PQRS"[int(key[2:]) - 1], modifier)
            return True
        sequence = special_sequence(self.style, key, modes.cursor_application_mode)
        if sequence is None:
            return False
        self._style_send(sequence, modifier)
        return True

    def _style_fkey(self, number: int, modifier: int) -> None:
        bits = modifier - 1
        if self.style in (KeyboardStyle.LEGACY, KeyboardStyle.VT220) and bits & 4:
            number += 12  # xterm's default ctrlFKeys bank
            modifier = (bits & ~4) + 1
        if (
            self.style is KeyboardStyle.VT220
            and modifier == constants.KEY_MOD_SHIFT
            and number in self.user_defined_keys
        ):
            self.board.transmit_keyboard_bytes(self.user_defined_keys[number])
            return
        sequence = function_sequence(self.style, number)
        if sequence is not None:
            self._style_send(sequence, modifier)

    def _style_numpad(self, key: str, modifier: int, *, numeric_override: bool = False) -> None:
        bits = modifier - 1
        if self.style is KeyboardStyle.VT220 and not bits & 1:
            if key == "+":
                key = ","
            if key == "," and bits & 4:
                key = "-"
                modifier = (bits & ~4) + 1
        if self.board.modes.numeric_keypad or numeric_override:
            text = {"Enter": "\r", "Tab": "\t", "Space": " "}.get(key, key)
            if len(text) == 1:
                self.board.transmit_keyboard(text, local_text=text, margin_key=text.isprintable())
            return
        final = {"=": "X", ",": "l", "Tab": "I", "Space": " "}.get(key)
        sequence = "\x1bO" + final if final else self.board.model.keymap.numpad_application.get(key)
        if sequence is not None:
            self._style_keypad_send(sequence, modifier)

    def _style_keypad_send(self, sequence: str, modifier: int) -> None:
        # Unlike cursor/function keys, keypad modifiers use original SS3 params.
        if self.style in (KeyboardStyle.LEGACY, KeyboardStyle.VT220):
            modifier, legacy_bits = 1, 0
        else:
            modifier, legacy_bits = self._special_modifier(modifier)
        sequence = modify_sequence(sequence, modifier, 0)
        if self._legacy_escape_prefix(legacy_bits):
            sequence = constants.ESC + sequence
        self.board.transmit_keyboard(sequence)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to the sequence for the current keypad mode."""
        if self.kitty_flags and key in KEYPAD_NAMES:
            text = key if self.board.modes.numeric_keypad and len(key) == 1 else None
            self.input_key_event(KeyEvent(KEYPAD_NAMES[key], text=text))
            return
        self._legacy_numpad(key)

    def _legacy_numpad(self, key: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        if self.style is not KeyboardStyle.DEFAULT:
            self._style_numpad(key, modifier)
            return
        keymap = self.board.model.keymap
        table = keymap.numpad_numeric if self.board.modes.numeric_keypad else keymap.numpad_application
        sequence = table.get(key, key)

        if modifier != constants.KEY_MOD_NONE:
            if self.board.modes.numeric_keypad:
                self._legacy_key(sequence, modifier)
            else:
                special_modifier, legacy_bits = self._special_modifier(modifier)
                if special_modifier != constants.KEY_MOD_NONE and keymap.modifiers:
                    sequence = apply_modifier(sequence, special_modifier)
                self._input_special(sequence, legacy_bits)
            return

        local_text = key if self.board.modes.numeric_keypad and len(key) == 1 else None
        self.input(sequence, local_text=local_text, margin_key=bool(local_text and local_text.isprintable()))

    def input_key_event(self, event: KeyEvent) -> None:
        """Encode supplied key facts using the child's active keyboard policy."""
        if event.event_type == "repeat" and not self.board.modes.auto_repeat:
            return
        flags = self.kitty_flags
        # Extended modifiers have no legacy encoding. Kitty-capable models can
        # express them even before an application opts into enhancements.
        if not flags and event.modifiers & (KeyModifiers.SUPER | KeyModifiers.HYPER):
            if KITTY_KEYBOARD not in self.board.model.provides:
                return
            flags = 1
        sequence = encode_key(event, flags)
        if sequence is not None:
            if sequence:
                text = event.text if event.event_type != "release" else None
                local_text = text
                if event.event_type != "release" and local_text is None:
                    key = ALIASES.get(event.key, event.key)
                    local_text = {"enter": "\r", "kp_enter": "\r", "tab": "\t", "backspace": "\x08"}.get(key)
                self.board.transmit_keyboard(sequence, local_text=local_text, margin_key=bool(text))
            return
        key = ALIASES.get(event.key, event.key)
        bits = int(event.modifiers)
        modifier = (bits & 7) + (8 if bits & KeyModifiers.META else 0) + 1
        if key.startswith("f") and key[1:].isdigit():
            self._legacy_fkey(int(key[1:]), modifier)
        elif key in KEYPAD_LEGACY:
            if (
                self.style is not KeyboardStyle.DEFAULT
                and bits & KeyModifiers.NUM_LOCK
                and self.board.modes.special_modifiers
                and event.text
                and len(event.text) == 1
            ):
                self._style_numpad(KEYPAD_LEGACY[key], modifier, numeric_override=True)
            else:
                self._legacy_numpad(KEYPAD_LEGACY[key], modifier)
        elif key.startswith("kp_"):
            modes = self.board.modes
            position = KEYPAD_POSITIONS.get(key[3:])
            if position is not None and (
                self.style is KeyboardStyle.VT220
                or (modes.application_escape and not modes.numeric_keypad and not modes.cursor_application_mode)
            ):
                self._legacy_numpad(position, modifier)
            else:
                self._legacy_key(key[3:], modifier)
        elif event.text and not bits & 62:
            self.board.transmit_keyboard(event.text, local_text=event.text, margin_key=True)
        elif event.text and len(event.text) > 1 and not bits & KeyModifiers.CTRL:
            prefix = constants.ESC if self._legacy_escape_prefix(modifier - 1) else ""
            self.board.transmit_keyboard(prefix + event.text, local_text=event.text, margin_key=True)
        else:
            char = {"escape": "\x1b", "enter": "\r", "tab": "\t", "backspace": "\x08"}.get(key, key)
            if event.text and len(event.text) == 1 and not bits & KeyModifiers.CTRL:
                char = event.text
            self._legacy_key(char, modifier)

    def input_text(self, text: str) -> None:
        """Committed text without a physical key (for example from an IME)."""
        if not valid_text(text):
            raise ValueError("committed text must not contain controls or surrogates")
        if not text:
            return
        if self.kitty_flags & 8:
            if self.kitty_flags & 16:
                for offset in range(0, len(text), 128):
                    chunk = text[offset : offset + 128]
                    self.board.transmit_keyboard(self._kitty_sequence(0, 1, chunk), local_text=chunk)
            return
        self.board.transmit_keyboard(text, local_text=text)

    def input_paste(self, text: str, phase: str = "complete") -> None:
        """A complete paste or bounded chunks of one bracketed transaction."""
        if phase not in ("complete", "start", "chunk", "end"):
            raise ValueError("invalid paste phase")
        if phase == "complete":
            data = f"\x1b[200~{text}\x1b[201~" if self.board.modes.bracketed_paste else text
        else:
            if phase == "start":
                self.paste_bracketed = self.board.modes.bracketed_paste
            prefix = "\x1b[200~" if phase == "start" and self.paste_bracketed else ""
            suffix = "\x1b[201~" if phase == "end" and self.paste_bracketed else ""
            data = prefix + text + suffix
        if data:
            self.board.transmit_keyboard(data, local_text=text)

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
