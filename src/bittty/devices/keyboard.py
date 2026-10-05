"""Keyboard input encoder for terminal key events."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .. import constants
from ..keyboard_protocol import ALIASES, KEYPAD_LEGACY, KEYPAD_NAMES, encode_key
from ..keyboard_styles import STYLE_KEYMAPS, KeyboardStyle
from ..keymap import DEC_FUNCTION_CODES, KEYPAD_POSITIONS, PF_KEYS, KeyMap, apply_modifier, vt52_keymap
from ..keys import LEGACY_MODIFIERS, KeyEvent, KeyModifiers, legacy_modifiers, valid_text, xterm_modifier
from ..charsets import KEYBOARD_LANGUAGES, KEYBOARD_NATIONAL_SETS, get_charset
from ..options import (
    XTERM_PASTE,
    DEC_KEY_MEMORY,
    DEC_KEYBOARD_DIALECT,
    DEC_KEYBOARD_LEDS,
    DEC_USER_KEYS,
    KITTY_KEYBOARD,
    XTERM_MODIFY_KEYS,
)
from .modes import ModeEffect

if TYPE_CHECKING:
    from ..operations import Operation
    from .board import Board
from .base import Device

M = KeyModifiers

# Raw input: DECCKM rewrites CSI A-D to SS3 A-D.
_NORMAL_CURSOR_KEY = re.compile(r"\x1b\[([ABCD])")

# All five enhancements are implemented by the explicit key-event encoder.
_KITTY_SUPPORTED = 31
# The spec: "Terminals should limit the size of the stack as appropriate, to
# prevent Denial-of-Service attacks." Full stack evicts its oldest entry.
_KITTY_STACK_MAX = 8
# xterm's key modifier resources (XTMODKEYS Pp) at their initial values: modifyKeyboard,
# modifyCursorKeys, modifyFunctionKeys, modifyKeypadKeys, modifyOtherKeys, (5, reserved),
# modifyModifierKeys and modifySpecialKeys. XTFMTKEYS formats start at 0: CSI 27 ; mod ; code ~.
# modifyKeyboard (the legacy/VT220 keyboards) and resources 3, 6 and 7 are stored and
# reported but change no encoding.
_MODIFY_KEYS_INITIAL = (0, 2, 2, 0, 0, 0, 0, 0)
_FORMAT_KEYS_INITIAL = (0,) * 8
# Named keys governed by modifyCursorKeys (1: the cursor and editing keypads) and
# modifyFunctionKeys (2: F1-F35). At level 4 they report CSI 27 ; mod ; code ~, where the
# code is the key's X keysym moved into the private-use area; Delete reports DEL (xterm 407).
_EXTENDED_KEYS = {
    **{
        name: (1, keysym - 0x1D00)
        for name, keysym in (
            ("home", 0xFF50), ("left", 0xFF51), ("up", 0xFF52), ("right", 0xFF53), ("down", 0xFF54),
            ("pageup", 0xFF55), ("pagedown", 0xFF56), ("end", 0xFF57), ("begin", 0xFF58),
            ("select", 0xFF60), ("insert", 0xFF63), ("find", 0xFF68),
        )
    },
    "delete": (1, 0x7F),
    **{f"f{n}": (2, 0xFFBE + n - 1 - 0x1D00) for n in range(1, 36)},
}  # fmt: skip
_EDITING_KEYPAD = frozenset({"insert", "delete", "pageup", "pagedown", "find", "select"})
# Xlib's Control translation (XLookupString) beyond '@'-'~': the digit and punctuation aliases.
_X_CONTROL_ALIASES = {
    " ": "\0",
    "2": "\0",
    "3": "\x1b",
    "4": "\x1c",
    "5": "\x1d",
    "6": "\x1e",
    "7": "\x1f",
    "8": "\x7f",
    "/": "\x1f",
}


# xterm's disallowedPasteControls (BS, DEL, ENQ, EOT, ESC and NUL), which it pastes as spaces.
_DISALLOWED_PASTE = str.maketrans(dict.fromkeys("\b\x7f\x05\x04\x1b\x00", " "))


def _x_control(char: str) -> str:
    """What Ctrl makes of a character in X: '@'-'~' become C0, a few aliases too, the rest are unchanged."""
    code = ord(char)
    return chr(code & 0x1F) if 0x40 <= code <= 0x7E else _X_CONTROL_ALIASES.get(char, char)


def _is_control(char: str) -> bool:
    code = ord(char)
    return code < 0x20 or 0x7F <= code <= 0x9F


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


# DECUDK numbers the definable keys F6-F20 by their VT220 codes.
_DECUDK_CODE_TO_FKEY = {code: n for n, code in enumerate(DEC_FUNCTION_CODES, 1) if n >= 6}


class KeyboardDevice(Device):
    """Encodes keyboard input into terminal control sequences."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.user_defined_keys: dict[int, bytes] = {}  # DECUDK: F-number -> wire bytes
        self.user_keys_locked = False
        self.style = KeyboardStyle.DEFAULT
        self.saved_style = KeyboardStyle.DEFAULT
        self.delete_mode: bool | None = None  # mode 1037, once set; else the keymap's default
        self.saved_delete_mode: bool | None = None
        self.modify_keys = list(_MODIFY_KEYS_INITIAL)  # XTMODKEYS resources
        self.format_keys = list(_FORMAT_KEYS_INITIAL)  # XTFMTKEYS resources
        # A terminal without xterm's modifier resources still negotiates modifyOtherKeys.
        self._modify_resources = range(8) if XTERM_MODIFY_KEYS in board.model.provides else (4,)
        self.paste_bracketed = False
        # Built directly: the blitter these key off does not exist yet.
        self._kitty = {False: _KittyState(), True: _KittyState()}
        # DECLL-loaded host indications. One set, not per-screen: LEDs are physical.
        self.led_num = False
        self.led_caps = False
        self.led_scroll = False
        self.leds_fitted = DEC_KEYBOARD_LEDS in board.model.provides
        # The keyboard: its language (North American) and whether its layout is enhanced PC.
        self.language = 1
        self.pc_layout = False
        self._national_keys: dict[int, str] = {}  # what national mode sends for a character
        self.handlers = {
            "XTMODKEYS": self.set_modify_keys,
        }
        if XTERM_MODIFY_KEYS in board.model.provides:
            self.handlers["XTQMODKEYS"] = self.report_modify_keys
            self.handlers["XTFMTKEYS"] = lambda op: self._set_resource(self.format_keys, _FORMAT_KEYS_INITIAL, op)
        if DEC_USER_KEYS in board.model.provides:
            self.handlers["DECUDK"] = self.set_user_keys
            self.handlers["DSR_USER_KEYS"] = self.report_user_keys
        if self.leds_fitted:
            self.handlers["DECLL"] = self.load_leds
        if board.model.keyboard_types is not None:
            self.handlers["DSR_KEYBOARD"] = self.report_keyboard
        if DEC_KEY_MEMORY in board.model.provides:
            self.handlers["DECPKA"] = self.program_key_action
            self.handlers["DECRQPKFM"] = self.report_key_memory
        if DEC_KEYBOARD_DIALECT in board.model.provides:
            self.handlers["DECKBD"] = self.select_keyboard
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

    def program_key_action(self, operation: Operation) -> None:
        """DECPKA — 1 locks the keys; 2 (factory defaults) and 3 (the saved definitions: bittty
        has no Set-Up to save any) clear them, unless they are locked."""
        action = operation.args[0]
        if action == 1:
            self.user_keys_locked = True
        elif action in (2, 3) and not self.user_keys_locked:
            self.user_defined_keys.clear()

    def report_key_memory(self, operation: Operation) -> None:
        """DECRQPKFM — DECPKFMR: the programmable keys' memory, total and free, in bytes."""
        total = self.board.model.udk_capacity
        free = total - sum(map(len, self.user_defined_keys.values()))
        self.board.host.write(f"\x1b[{total};{free}+y", flush=True)

    def report_user_keys(self, operation: Operation) -> None:
        """DSR 25 reports the download lock, not the keyboard action lock."""
        self.board.host.write(f"\x1b[?{21 if self.user_keys_locked else 20}n", flush=True)

    def set_user_keys_locked(self, locked: bool) -> None:
        """Operator Set-Up control; DECUDK cannot unlock downloaded keys."""
        self.user_keys_locked = locked

    # --- modern keyboard negotiation (xterm modifyOtherKeys, Kitty protocol) --- #

    @property
    def modify_other_keys(self) -> int:
        """xterm modifyOtherKeys level (0/1/2)."""
        return self.modify_keys[4]

    def set_modify_keys(self, operation: Operation) -> None:
        """XTMODKEYS (CSI > Pp ; Pv m) — set a key-modifier resource, or restore it without Pv."""
        self._set_resource(self.modify_keys, _MODIFY_KEYS_INITIAL, operation)

    def _set_resource(self, values: list[int], initial: tuple[int, ...], operation: Operation) -> None:
        """Set an XTMODKEYS/XTFMTKEYS resource. As in xterm 407, a bare CSI > m (or f) restores nothing."""
        params = operation.args[0]
        resource = params[0] if params else None
        if resource in self._modify_resources and resource != 5:  # 5 is reserved
            values[resource] = params[1] if len(params) > 1 and params[1] is not None else initial[resource]

    def report_modify_keys(self, operation: Operation) -> None:
        """XTQMODKEYS (CSI ? Pp m) — answer in XTMODKEYS form, so the reply restores the setting."""
        resource = operation.args[0]
        if resource in self._modify_resources:
            self.board.host.write(f"{constants.ESC}[>{resource};{self.modify_keys[resource]}m", flush=True)

    def _extended_key(self, code: int, mods: KeyModifiers, resource: int) -> str:
        """xterm's CSI 27 ; mod ; code ~, or CSI code ; mod u when the resource's format is 1."""
        modifier = xterm_modifier(mods)
        if self.format_keys[resource]:
            return f"{constants.ESC}[{code};{modifier}u"
        return f"{constants.ESC}[27;{modifier};{code}~"

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

    def report_keyboard(self, operation: Operation) -> None:
        """DSR — the keyboard language; and, past the VT220, its status (ready) and type."""
        types = self.board.model.keyboard_types
        fields = f";0;{types[self.pc_layout]}" if types else ""
        self.board.host.write(f"\x1b[?27;{self.language}{fields}n", flush=True)

    def select_keyboard(self, operation: Operation) -> None:
        """DECKBD — the keyboard layout (VT, or 2: enhanced PC) and language; anything else is ignored."""
        layout, language = operation.args
        if layout not in (0, 1, 2) or language not in KEYBOARD_LANGUAGES:
            return
        self.pc_layout = layout == 2
        self.language = language or 1
        national = get_charset(KEYBOARD_NATIONAL_SETS.get(self.language, "B"))
        self._national_keys = {ord(char): code for code, char in national.items()}

    def _national(self, text: str) -> str:
        """In national mode the keyboard sends its language's national replacement set."""
        return text.translate(self._national_keys) if self.board.modes.national_charset_mode else text

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
        if modes.mode_status(True, 110) == 2:  # DECKLHIM known and reset
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

    def _modify_other_keys(self, char: str, mods: KeyModifiers) -> str | None:
        """xterm modifyOtherKeys for a character key: CSI 27 ; mod ; code ~, else None.

        Ported from xterm input.c (ModifyOtherKeys, allowedCharModifiers). Level 1
        leaves keys whose modified form already means something alone (Ctrl-letter,
        Shift-printable, Ctrl-2 as NUL, Escape, Backspace); level 2 reports those
        too, except Shift on characters below '@'. The code is the shifted
        character: what the key types without Ctrl. Kitty flags take precedence.
        """
        level = self.modify_other_keys
        if not level or not mods or self.kitty_flags:
            return None
        if char == constants.BS:
            # xterm's backarrow toggle: a Backspace that sends DEL is reported as DEL, without Ctrl.
            if self.board.modes.backarrow_key_sends_bs == bool(mods & M.CTRL):
                char, mods = constants.DEL, mods & ~M.CTRL
                encode = level >= 2 and bool(mods)
            else:
                encode = level >= 2 and bool(mods & ~M.CTRL)
        elif level >= 2:
            if char == "\t" and mods & M.SHIFT:  # backtab (ISO_Left_Tab)
                encode = bool(mods & ~M.SHIFT)
            elif char in "\t\r\x1b\x7f":
                encode = True
            else:
                char = char.upper() if mods & M.SHIFT and len(char.upper()) == 1 else char
                encode = 0x40 <= ord(char) <= 0x7F or (mods == M.SHIFT and char == " ") or bool(mods & ~M.SHIFT)
        else:
            if not (char == "\t" and mods & M.SHIFT):
                char = char.upper() if mods & M.SHIFT and len(char.upper()) == 1 else char
            mods = self._filter_alt_meta(mods, char)
            if char in "\t\r" and not (char == "\t" and mods & M.SHIFT):
                encode = bool(mods)
            elif char in "\t\x1b":  # backtab and Escape are control aliases already
                encode = bool(mods & ~(M.CTRL | M.SHIFT))
            elif char == "\x7f":
                encode = False
            else:
                control_input = 0x40 <= ord(char) <= 0x7F
                alias = _is_control(_x_control(char) if mods & M.CTRL else char)
                if control_input and not mods & ~M.CTRL:
                    pass
                elif alias:
                    mods = mods if mods & ~(M.CTRL | M.SHIFT) else M.NONE
                elif not mods & M.CTRL:
                    mods &= ~M.SHIFT
                if control_input:
                    encode = mods not in (M.NONE, M.CTRL, M.SHIFT)
                elif alias:
                    encode = bool(mods & ~M.CTRL) and mods != M.SHIFT
                else:
                    encode = bool(mods)
        if not encode:
            return None
        return self._extended_key(ord(char), mods, 4)

    def _filter_alt_meta(self, mods: KeyModifiers, char: str) -> KeyModifiers:
        """Leave Alt/Meta to the legacy encodings at level 1 (xterm filterAltMeta).

        Escape-prefix modes claim them, a bare Alt/Meta stays legacy, and
        Ctrl-Alt on a control character keeps its emacs meaning.
        """
        modes = self.board.modes
        control = char not in "\t\r\x1b\x7f" and (0x40 <= ord(char) <= 0x7F or _is_control(char))
        for mask, escapes in ((M.META, modes.meta_sends_escape), (M.ALT, modes.alt_sends_escape)):
            if mods & mask:
                if escapes or not mods & ~mask:
                    mods &= ~mask
                if control and mods & M.CTRL:
                    mods &= ~(mask | M.CTRL)
        return mods

    def report_focus(self, focused: bool) -> None:
        """Focus reporting (DECSET 1004) — send CSI I on focus in, CSI O on focus out."""
        if self.board.modes.focus_reporting:
            self.board.host.write(f"{constants.ESC}[I" if focused else f"{constants.ESC}[O", flush=True)

    def reset(self, hard: bool = True) -> None:
        """RIS clears the modern-keyboard negotiation state, on both screens.

        Both resets restore xterm's key modifier resources, as xterm 407 does.
        """
        self.modify_keys[:] = _MODIFY_KEYS_INITIAL
        self.format_keys[:] = _FORMAT_KEYS_INITIAL
        if hard:
            # Xterm keyboard selection survives RIS, unlike its saved slot.
            self.saved_style = KeyboardStyle.DEFAULT
            self.saved_delete_mode = None  # the setting itself survives, like the keyboard selection
            self.user_defined_keys.clear()
            self.user_keys_locked = False
            for state in self._kitty.values():
                state.clear()
            self.led_num = self.led_caps = self.led_scroll = False

    @property
    def keyboard_selected(self) -> bool:
        """Whether an xterm keyboard (Sun/HP/SCO/legacy/VT220) replaces the model's keymap."""
        return self.style is not KeyboardStyle.DEFAULT

    @property
    def keymap(self) -> KeyMap:
        """The active keymap: an xterm keyboard selection, else the model's own; in VT52 mode, its VT52 form."""
        keymap = STYLE_KEYMAPS.get(self.style, self.board.model.keymap)
        return keymap if self.board.modes.ansi_mode else vt52_keymap(keymap)

    def _legacy_escape_prefix(self, mods: KeyModifiers) -> bool:
        """Whether legacy Alt/Meta policy prefixes this input with ESC."""
        modes = self.board.modes
        return bool((mods & M.ALT and modes.alt_sends_escape) or (mods & M.META and modes.meta_sends_escape))

    def _send_key(self, sequence: str, mods: KeyModifiers, *, keypad: bool = False, placement: int = 2) -> None:
        """Send a keymap sequence, folding in the modifiers if the keymap encodes them."""
        keymap = self.keymap
        modifiers = keymap.modifiers or (keymap.modifiers_with_other_keys and self.modify_other_keys)
        if modifiers and (keymap.keypad_modifiers or not keypad):
            sequence = apply_modifier(sequence, xterm_modifier(mods), keypad=keypad, placement=placement)
        elif keypad and keymap.keypad_meta_prefix and mods & (M.ALT | M.META):
            sequence = constants.ESC + sequence
        self.board.transmit_keyboard(sequence)

    @property
    def delete_sends_del(self) -> bool:
        """Mode 1037 as set, else the keymap's default; keymaps with their own Delete never send DEL."""
        policy = self.keymap.delete_is_del
        return policy is not None and (policy if self.delete_mode is None else self.delete_mode)

    def _delete_is_del(self, mods: KeyModifiers) -> bool:
        """Whether this Delete press sends DEL rather than the keymap's Delete sequence.

        Raw DEL recreates the ambiguity Kitty flag 1 removes, so negotiated
        Kitty flags keep the keymap's CSI 3~; so does a modified Delete under
        modifyOtherKeys (xterm).
        """
        return self.delete_sends_del and not self.kitty_flags and not (mods and self.modify_other_keys)

    def _named_key(self, name: str, mods: KeyModifiers) -> None:
        """Encode a named key from the active keymap; names it does not define are ignored."""
        keymap = self.keymap
        # DECCKM's SS3 forms are legacy encodings; Kitty ignores the mode.
        application = keymap.application if self.board.modes.cursor_application_mode and not self.kitty_flags else {}
        modified = keymap.modified if mods else {}
        sequence = modified.get(name) or application.get(name) or keymap.keys.get(name)
        if sequence is None:
            return
        resource, code = _EXTENDED_KEYS.get(name, (None, None))
        level = self.modify_keys[resource] if resource and keymap.modifiers else 2
        if level >= 4:
            self.board.transmit_keyboard(self._extended_key(code, mods, resource))
            return
        placement = 2 if name in _EDITING_KEYPAD else level  # below 4, xterm leaves these alone
        self._send_key(sequence, mods, keypad=name in PF_KEYS, placement=placement)

    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert key + modifier to standard control codes, then send to input()."""
        mods = legacy_modifiers(modifier)
        if self.kitty_flags:
            key = chr(self._kitty_code(char)) if len(char) == 1 and char not in ALIASES else char
            self.input_key_event(KeyEvent(key, mods, text=char if len(char) == 1 and valid_text(char) else None))
            return
        self._legacy_key(char, mods)

    def _legacy_key(self, char: str, mods: KeyModifiers) -> None:
        if char == "escape":
            char = constants.ESC
        if char == "delete":  # the editing keypad's Delete, not KP_Delete
            if self._delete_is_del(mods):
                self.board.transmit_keyboard(constants.DEL)
                return
            if self.keymap.delete_unmodified and not self.modify_other_keys:
                mods = M.NONE
        if len(char) > 1:
            self._named_key(char, mods)
            return

        other_key = self._modify_other_keys(char, mods)
        if other_key is not None:
            self.input(other_key, local_text=char, margin_key=char.isprintable())
            return

        local_text = char
        if char == constants.BS:
            # Ctrl sends whichever of BS and DEL the backarrow key does not; echo stays a backspace.
            if self.board.modes.backarrow_key_sends_bs == bool(mods & M.CTRL):
                char = constants.DEL
            mods &= ~M.CTRL

        backtab = self.keymap.keys.get("backtab") if char == "\t" and mods & M.SHIFT else None
        if backtab is not None:  # xterm folds no modifiers into CSI Z
            self.board.transmit_keyboard(backtab)
            return

        if char == constants.ESC:
            if self.board.modes.application_escape:
                self.input("\x1bO[")
                return
            char = local_text = "\x1c" if self.board.modes.escape_sends_fs else constants.ESC

        # Apply the legacy control and Alt transformations only after the
        # negotiated modern encodings above have had first refusal.
        if mods & M.CTRL:
            char = local_text = "\x7f" if char == "?" else _x_control(char)  # xterm: Ctrl-? is DEL

        # Escape-prefix policy wins over the older eighth-bit Meta form.
        if self._legacy_escape_prefix(mods):
            char = constants.ESC + char
        elif mods & (M.ALT | M.META) and self.board.modes.eight_bit_input and ord(char) < 128:
            char = chr(ord(char) | 0x80)  # xterm in a UTF-8 locale sends the shifted code as a character
        self.input(char, local_text=local_text, margin_key=local_text.isprintable())

    def input_fkey(self, num: int, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Encode a function key using any user-defined string, else the keymap."""
        self.input_key_event(KeyEvent(f"f{num}", legacy_modifiers(modifier)))

    def _legacy_fkey(self, num: int, mods: KeyModifiers) -> None:
        keymap = self.keymap
        if mods & M.CTRL and keymap.ctrl_function_offset:  # xterm ctrlFKeys: a second bank, unmodified
            num += keymap.ctrl_function_offset
            mods &= ~M.CTRL
        if keymap.user_keys and mods == M.SHIFT and num in self.user_defined_keys:
            self.board.transmit_keyboard_bytes(self.user_defined_keys[num])
            return
        self._named_key(f"f{num}", mods)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to the sequence for the current keypad mode."""
        if self.kitty_flags and key in KEYPAD_NAMES:
            text = key if self.board.modes.numeric_keypad and len(key) == 1 else None
            self.input_key_event(KeyEvent(KEYPAD_NAMES[key], text=text))
            return
        self._legacy_numpad(key, M.NONE)

    def _legacy_numpad(self, key: str, mods: KeyModifiers, *, numeric: bool = False) -> None:
        """Encode a keypad key: text in numeric mode (or when forced), else its DECKPAM sequence."""
        keymap = self.keymap
        if keymap.vt220_keypad and not mods & M.SHIFT:
            key = {"+": ","}.get(key, key)
            if key == "," and mods & M.CTRL:
                key, mods = "-", mods & ~M.CTRL
        if numeric or self.board.modes.numeric_keypad:
            # A keymap may give a modified keypad key its own text (xterm's termcap keys).
            text = (mods and keymap.modified.get(f"kp_{key.lower()}")) or keymap.numeric.get(key)
            if text is not None:
                prefix = constants.ESC if keymap.keypad_meta_prefix and mods & (M.ALT | M.META) else ""
                self.board.transmit_keyboard(prefix + text, local_text=text, margin_key=text.isprintable())
            return
        sequence = keymap.keypad.get(key)
        if sequence is not None:
            self._send_key(sequence, mods, keypad=True)

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
        bits = event.modifiers
        mods = bits & LEGACY_MODIFIERS
        if key.startswith("f") and key[1:].isdigit():
            self._legacy_fkey(int(key[1:]), mods)
        elif key in KEYPAD_LEGACY:
            # xterm numLock (mode 1035, known and set): with NumLock on, the keypad
            # sends its text even under DECKPAM. Other terminals keep DECKPAM.
            numeric = bool(
                bits & KeyModifiers.NUM_LOCK
                and self.board.modes.mode_status(True, 1035) == 1
                and event.text
                and len(event.text) == 1
            )
            self._legacy_numpad(KEYPAD_LEGACY[key], mods, numeric=numeric)
        elif key.startswith("kp_"):
            modes = self.board.modes
            position = KEYPAD_POSITIONS.get(key[3:])
            if position is not None and (
                self.keymap.vt220_keypad
                or (modes.application_escape and not modes.numeric_keypad and not modes.cursor_application_mode)
            ):
                self._legacy_numpad(position, mods)
            else:
                self._named_key(key[3:], mods)
        elif event.text and not bits & 62 and not (bits & M.SHIFT and self.modify_other_keys >= 2):
            self.board.transmit_keyboard(self._national(event.text), local_text=event.text, margin_key=True)
        elif event.text and len(event.text) > 1 and not bits & KeyModifiers.CTRL:
            prefix = constants.ESC if self._legacy_escape_prefix(mods) else ""
            self.board.transmit_keyboard(prefix + self._national(event.text), local_text=event.text, margin_key=True)
        else:
            char = {"escape": "\x1b", "enter": "\r", "tab": "\t", "backspace": "\x08"}.get(key, key)
            if event.text and len(event.text) == 1 and not bits & KeyModifiers.CTRL:
                char = event.text
            elif bits & M.SHIFT and event.shifted_key:
                char = event.shifted_key
            self._legacy_key(char, mods)

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
        self.board.transmit_keyboard(self._national(text), local_text=text)

    def input_paste(self, text: str, phase: str = "complete") -> None:
        """A complete paste or bounded chunks of one bracketed transaction."""
        if phase not in ("complete", "start", "chunk", "end"):
            raise ValueError("invalid paste phase")
        if phase == "start":
            self.paste_bracketed = self.board.modes.bracketed_paste
        bracketed = self.board.modes.bracketed_paste if phase == "complete" else self.paste_bracketed
        prefix = "\x1b[200~" if bracketed and phase in ("complete", "start") else ""
        suffix = "\x1b[201~" if bracketed and phase in ("complete", "end") else ""
        if XTERM_PASTE in self.board.model.provides:
            self._paste_as_xterm(prefix, text, suffix)
        elif prefix + text + suffix:
            self.board.transmit_keyboard(prefix + text + suffix, local_text=text)

    def _paste_as_xterm(self, prefix: str, text: str, suffix: str) -> None:
        """Newlines as carriage returns (unless mode 2006), disallowed controls as spaces, and
        under mode 2005 each byte quoted with Ctrl-V (literal-next)."""
        modes = self.board.modes
        pasted = text.translate(_DISALLOWED_PASTE)
        if not modes.readline_newline:
            pasted = pasted.replace("\n", "\r")
        if not modes.readline_quoting:
            if prefix + pasted + suffix:
                self.board.transmit_keyboard(prefix + pasted + suffix, local_text=text)
            return
        quoted = b"".join(b"\x16" + bytes([byte]) for byte in pasted.encode())
        self.board.transmit_keyboard_bytes(prefix.encode() + quoted + suffix.encode(), local_text=text)

    def input(self, data: str, *, local_text: str | None = None, margin_key: bool = False) -> None:
        """Translate control codes based on terminal modes and send to the host."""
        # DECCKM's SS3 forms are legacy encodings; Kitty ignores the mode.
        if self.board.modes.cursor_application_mode and not self.kitty_flags and f"{constants.ESC}[" in data:
            data = self.translate_application_cursor_keys(data)
        self.board.transmit_keyboard(data, local_text=local_text, margin_key=margin_key)

    @staticmethod
    def translate_application_cursor_keys(data: str) -> str:
        """Translate embedded normal cursor-key CSI sequences to application mode."""
        return _NORMAL_CURSOR_KEY.sub("\x1bO\\1", data)
