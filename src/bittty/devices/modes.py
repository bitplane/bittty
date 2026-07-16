"""Terminal modes as a declarative capability table.

Each mode is a small `Mode` capability that claims a number (ANSI or DEC
private), knows how to apply itself and how to report its DECRQM status, and
can be omitted by a personality (so, e.g., a terminal that predates bracketed
paste simply does not recognise mode 2004). The boolean flags themselves stay
as attributes on the device: they are read widely across the emulator, and
several modes legitimately share one flag (mode 7 and 1000 both drive
`mouse_tracking`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

from .. import constants
from ..operations import Operation
from .base import Device

if TYPE_CHECKING:
    from .board import TerminalBoard


@dataclass(frozen=True)
class Mode:
    """One terminal mode: which flag it backs and how it answers DECRQM."""

    number: int
    private: bool
    attr: Optional[str] = None  # device flag this mode drives, if any
    invert: bool = False  # "set" stores the negation (modes 12, 66)
    queryable: bool = False  # DECRQM reports this mode's state
    apply_fn: Optional[Callable[["ModeDevice", bool], None]] = None  # side effect
    status_fn: Optional[Callable[["ModeDevice"], int]] = None  # custom DECRQM status

    @property
    def key(self) -> tuple[bool, int]:
        return (self.private, self.number)

    def apply(self, device: ModeDevice, value: bool) -> None:
        if self.attr is not None:
            setattr(device, self.attr, (not value) if self.invert else value)
        if self.apply_fn is not None:
            self.apply_fn(device, value)

    def status(self, device: ModeDevice) -> int:
        """DECRQM status: 1 = set, 2 = reset, 0 = not recognised."""
        if self.status_fn is not None:
            return self.status_fn(device)
        if self.queryable and self.attr is not None:
            state = getattr(device, self.attr)
            return 1 if ((not state) if self.invert else state) else 2
        return 0


# --- side effects for modes that do more than flip a flag --- #


def _deccolm(device: ModeDevice, value: bool) -> None:
    device.board.resize(132 if value else 80, device.board.height)


def _alt_screen(device: ModeDevice, value: bool) -> None:
    device.board.screen.switch_screen(value)


def _save_restore_cursor(device: ModeDevice, value: bool) -> None:
    if value:
        device.board.cursor.save()
    else:
        device.board.cursor.restore()


def _alt_screen_and_cursor(device: ModeDevice, value: bool) -> None:
    if value:
        device.board.cursor.save()
        device.board.screen.switch_screen(True)
    else:
        device.board.screen.switch_screen(False)
        device.board.cursor.restore()


def _mouse_button_tracking(device: ModeDevice, value: bool) -> None:
    device.mouse_tracking = value
    device.mouse_button_tracking = value


def _mouse_any_tracking(device: ModeDevice, value: bool) -> None:
    device.mouse_tracking = value
    device.mouse_any_tracking = value


def _declrmm(device: ModeDevice, value: bool) -> None:
    # Disabling left/right margin mode resets the margins to the full width.
    if not value:
        device.board.screen.reset_left_right_margins()


def _column_status(device: ModeDevice) -> int:
    return 1 if device.board.width == 132 else 2


def _alt_screen_status(device: ModeDevice) -> int:
    return 1 if device.board.screen.in_alt_screen else 2


def _mouse_button_status(device: ModeDevice) -> int:
    return 1 if device.mouse_button_tracking else 2


def _mouse_any_status(device: ModeDevice) -> int:
    return 1 if device.mouse_any_tracking else 2


# The full mode repertoire. A personality may omit any of these.
MODE_SPECS: list[Mode] = [
    # ANSI modes (autowrap and cursor visibility are DEC *private* 7/25, not ANSI)
    Mode(2, False, "keyboard_action_mode", queryable=True),  # KAM
    Mode(4, False, "insert_mode", queryable=True),
    Mode(12, False, "local_echo", invert=True, queryable=True),
    Mode(20, False, "linefeed_newline_mode", queryable=True),
    Mode(constants.DECKPAM_APPLICATION_KEYPAD, False, "application_keypad", queryable=True),
    # DEC private modes
    Mode(1, True, "cursor_application_mode", queryable=True),
    Mode(2, True, "ansi_mode", queryable=True),
    Mode(3, True, apply_fn=_deccolm, status_fn=_column_status),
    Mode(4, True, "scroll_mode", queryable=True),
    Mode(5, True, "reverse_screen", queryable=True),
    Mode(6, True, "origin_mode", queryable=True),
    Mode(7, True, "auto_wrap", queryable=True),
    Mode(8, True, "auto_repeat", queryable=True),
    Mode(9, True, "mouse_tracking", queryable=True),
    Mode(12, True, "cursor_blinking", queryable=True),
    Mode(20, True, "linefeed_newline_mode", queryable=True),
    Mode(25, True, "cursor_visible", queryable=True),
    Mode(47, True, apply_fn=_alt_screen, status_fn=_alt_screen_status),
    Mode(66, True, "numeric_keypad", invert=True, queryable=True),
    Mode(67, True, "backarrow_key_sends_bs", queryable=True),
    Mode(68, True, "keyboard_usage_mode", queryable=True),  # DECKBUM
    Mode(69, True, "left_right_margin_mode", queryable=True, apply_fn=_declrmm),  # DECLRMM
    Mode(1000, True, "mouse_tracking", queryable=True),
    Mode(1004, True, "focus_reporting", queryable=True),
    Mode(1002, True, apply_fn=_mouse_button_tracking, status_fn=_mouse_button_status),
    Mode(1003, True, apply_fn=_mouse_any_tracking, status_fn=_mouse_any_status),
    Mode(1006, True, "mouse_sgr_mode", queryable=True),
    Mode(1015, True, "urxvt_mouse", queryable=True),
    Mode(1047, True, apply_fn=_alt_screen, status_fn=_alt_screen_status),
    Mode(1048, True, apply_fn=_save_restore_cursor),
    Mode(1049, True, apply_fn=_alt_screen_and_cursor, status_fn=_alt_screen_status),
    # Extended xterm private modes — mostly stored state a frontend actuates.
    Mode(40, True, "allow_column_mode", queryable=True),  # permit DECCOLM 80<->132
    Mode(42, True, "national_charset_mode", queryable=True),  # DECNRCM
    Mode(44, True, "margin_bell", queryable=True),
    Mode(45, True, "reverse_wraparound", queryable=True),  # xterm reverse-wraparound
    Mode(80, True, "sixel_display_mode", queryable=True),  # DECSDM
    Mode(1001, True, "mouse_highlight_tracking", queryable=True),  # VT200 hilite tracking
    Mode(1005, True, "mouse_utf8_mode", queryable=True),
    Mode(1007, True, "alternate_scroll_mode", queryable=True),
    Mode(1016, True, "mouse_pixel_mode", queryable=True),  # SGR-pixels
    Mode(1036, True, "meta_sends_escape", queryable=True),
    Mode(1039, True, "alt_sends_escape", queryable=True),
    Mode(1042, True, "bell_urgency", queryable=True),  # urgency hint on bell
    Mode(1043, True, "bell_raise", queryable=True),  # raise window on bell
    Mode(1046, True, "allow_alt_screen", queryable=True),  # permit 1047/1049 switching
    Mode(2004, True, "bracketed_paste", queryable=True),
    Mode(2026, True, "synchronized_output", queryable=True),
    Mode(2027, True, "grapheme_clustering", queryable=True),
    Mode(2028, True, "auto_resize_mode", queryable=True),
    Mode(2031, True, "color_scheme_updates", queryable=True),  # report light/dark changes
]


class ModeDevice(Device):
    """Owns terminal mode state and applies mode operations via the mode table."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self._set_defaults()
        unsupported = board.personality.unsupported_modes
        self._modes = {mode.key: mode for mode in MODE_SPECS if mode.key not in unsupported}
        self.handlers = {
            "SM": self.apply_mode_operation,
            "RM": self.apply_mode_operation,
            "DECSET": self.apply_mode_operation,
            "DECRST": self.apply_mode_operation,
            "DECKPAM": self.enter_application_keypad,
            "DECKPNM": self.enter_numeric_keypad,
        }

    def _set_defaults(self) -> None:
        """Set every mode flag to its power-on default."""
        self.auto_wrap = True
        self.insert_mode = False
        self.application_keypad = False
        self.ansi_mode = True
        self.cursor_application_mode = False
        self.cursor_visible = True
        self.cursor_blinking = False
        self.scroll_mode = False
        self.mouse_tracking = False
        self.mouse_button_tracking = False
        self.mouse_any_tracking = False
        self.mouse_sgr_mode = False
        self.mouse_extended_mode = False
        self.urxvt_mouse = False
        self.backarrow_key_sends_bs = False
        self.auto_repeat = True
        self.numeric_keypad = True
        self.local_echo = True
        self.reverse_screen = False
        self.linefeed_newline_mode = False
        self.origin_mode = False
        self.auto_resize_mode = False
        self.keyboard_usage_mode = False
        self.left_right_margin_mode = False
        self.focus_reporting = False
        self.synchronized_output = False
        self.bracketed_paste = False
        # Extended xterm private modes (stored state; frontend actuates most).
        self.keyboard_action_mode = False
        self.allow_column_mode = False
        self.national_charset_mode = False
        self.margin_bell = False
        self.reverse_wraparound = False
        self.sixel_display_mode = False
        self.mouse_highlight_tracking = False
        self.mouse_utf8_mode = False
        self.alternate_scroll_mode = False
        self.mouse_pixel_mode = False
        self.meta_sends_escape = False
        self.alt_sends_escape = False
        self.bell_urgency = False
        self.bell_raise = False
        self.allow_alt_screen = True  # alt-screen switching permitted by default
        self.grapheme_clustering = False
        self.color_scheme_updates = False

    def reset(self, hard: bool = True) -> None:
        """Reset modes. hard restores every flag (RIS); soft is the DECSTR subset."""
        if hard:
            self._set_defaults()
            return
        # DECSTR soft reset — the widely-agreed subset (SGR is reset by the style device).
        self.insert_mode = False
        self.origin_mode = False
        self.cursor_visible = True

    # --- dispatch --- #

    def apply_mode_operation(self, operation: Operation) -> None:
        params, set_mode, private = operation.args
        modes = self.set_private_modes if private else self.set_ansi_modes
        modes(params, set_mode)

    def enter_application_keypad(self, operation: Operation) -> None:
        self.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, True)
        self.numeric_keypad = False

    def enter_numeric_keypad(self, operation: Operation) -> None:
        self.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, False)
        self.numeric_keypad = True

    # --- applying modes --- #

    def _apply(self, private: bool, param: int | None, value: bool) -> None:
        if param is None:
            return
        mode = self._modes.get((private, param))
        if mode is not None:
            mode.apply(self, value)

    def set_ansi_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            self._apply(False, param, set_mode)

    def set_private_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            self._apply(True, param, set_mode)

    def set_mode(self, mode: int, value: bool = True, private: bool = False) -> None:
        """Set a single terminal mode."""
        self._apply(private, mode, value)

    def clear_mode(self, mode: int, private: bool = False) -> None:
        """Clear a single terminal mode."""
        self._apply(private, mode, False)

    # --- DECRQM status --- #

    def get_private_mode_status(self, mode: int) -> int:
        entry = self._modes.get((True, mode))
        return entry.status(self) if entry is not None else 0

    def get_ansi_mode_status(self, mode: int) -> int:
        entry = self._modes.get((False, mode))
        return entry.status(self) if entry is not None else 0
