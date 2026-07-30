"""Terminal modes as a declarative capability table.

Each mode is a small `Mode` capability that claims a number (ANSI or DEC
private), knows how to apply itself and how to report its DECRQM status, and
can be omitted by a model (so, e.g., a terminal that predates bracketed
paste simply does not recognise mode 2004). The boolean flags themselves stay
as attributes on the device: they are read widely across the emulator, and
several modes legitimately share one flag (mode 7 and 1000 both drive
`mouse_tracking`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from ..operations import Operation
from ..present import (
    AmbiguousWidthChanged,
    CursorBlinkChanged,
    CursorVisibilityChanged,
    GraphemeClusteringChanged,
    MouseModeChanged,
    ReverseScreenChanged,
    SyncOutputChanged,
)
from .base import Device

if TYPE_CHECKING:
    from .board import Board


@dataclass(frozen=True)
class Mode:
    """One terminal mode: which flag it backs and how it answers DECRQM."""

    number: int
    private: bool
    attr: str | None = None  # device flag this mode drives, if any
    invert: bool = False  # "set" stores the negation (modes 12, 66)
    queryable: bool = False  # DECRQM reports this mode's state
    apply_fn: Callable[["ModeDevice", bool], None] | None = None  # side effect
    status_fn: Callable[["ModeDevice"], int] | None = None  # custom DECRQM status
    peripheral: str | None = None  # emit a corresponding present event on change

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
    # xterm ignores DECCOLM unless mode 40 permits it — reset strings carry ?3l,
    # and honouring it ungated shrinks any wider terminal to 80 columns.
    if device.allow_column_mode:
        device.board.blitter.set_column_mode(132 if value else 80)


def _alt_screen(device: ModeDevice, value: bool) -> None:
    if device.allow_alt_screen:
        device.board.blitter.switch_screen(value)
        device._emit_peripheral("mouse")


def _save_restore_cursor(device: ModeDevice, value: bool) -> None:
    if not device.allow_alt_screen:
        return
    if value:
        device.board.cursor.save()
    else:
        device.board.cursor.restore()


def _alt_screen_and_cursor(device: ModeDevice, value: bool) -> None:
    if not device.allow_alt_screen:
        return
    if value:
        device.board.cursor.save()
        device.board.blitter.switch_screen(True)
    else:
        device.board.blitter.switch_screen(False)
        device.board.cursor.restore()
    device._emit_peripheral("mouse")


def _allow_alt_screen(device: ModeDevice, value: bool) -> None:
    if not value:
        device.board.blitter.switch_screen(False)
        device._emit_peripheral("mouse")


def _mouse_button_tracking(device: ModeDevice, value: bool) -> None:
    device.mouse_tracking = value
    device.mouse_button_tracking = value


def _mouse_any_tracking(device: ModeDevice, value: bool) -> None:
    device.mouse_tracking = value
    device.mouse_any_tracking = value


def _declrmm(device: ModeDevice, value: bool) -> None:
    if value:
        # Horizontal margins and row-wide double-size attributes cannot coexist.
        device.board.blitter.primary_buffer.reset_line_attributes()
        device.board.blitter.alt_buffer.reset_line_attributes()
    else:
        # Disabling left/right margin mode resets the margins to the full width.
        device.board.blitter.reset_left_right_margins()


def _column_status(device: ModeDevice) -> int:
    return 1 if device.board.width == 132 else 2


def _alt_screen_status(device: ModeDevice) -> int:
    return 1 if device.board.blitter.in_alt_screen else 2


def _mouse_button_status(device: ModeDevice) -> int:
    return 1 if device.mouse_button_tracking else 2


def _mouse_any_status(device: ModeDevice) -> int:
    return 1 if device.mouse_any_tracking else 2


def _ambiguous_width(device: ModeDevice, value: bool) -> None:
    device.board.set_ambiguous_width(2 if value else 1)


def _grapheme_clustering(device: ModeDevice, value: bool) -> None:
    device.board.blitter.set_grapheme_clustering(value)


def _print_form_feed(device: ModeDevice, value: bool) -> None:
    device.board.printer.print_form_feed = value


def _print_form_feed_status(device: ModeDevice) -> int:
    return 1 if device.board.printer.print_form_feed else 2


def _print_extent(device: ModeDevice, value: bool) -> None:
    device.board.printer.print_extent = value


def _print_extent_status(device: ModeDevice) -> int:
    return 1 if device.board.printer.print_extent else 2


# Implemented mode repertoire. A model may omit any of these.
MODE_SPECS: list[Mode] = [
    # ANSI modes (autowrap and cursor visibility are DEC *private* 7/25, not ANSI)
    Mode(4, False, "insert_mode", queryable=True),
    Mode(20, False, "linefeed_newline_mode", queryable=True),
    # DEC private modes
    Mode(1, True, "cursor_application_mode", queryable=True),
    Mode(3, True, apply_fn=_deccolm, status_fn=_column_status),
    Mode(5, True, "reverse_screen", queryable=True, peripheral="reverse"),
    Mode(6, True, "origin_mode", queryable=True),
    Mode(7, True, "auto_wrap", queryable=True),
    Mode(9, True, "mouse_tracking", queryable=True, peripheral="mouse"),
    Mode(12, True, "cursor_blinking", queryable=True, peripheral="cursor_blink"),
    Mode(18, True, apply_fn=_print_form_feed, status_fn=_print_form_feed_status),
    Mode(19, True, apply_fn=_print_extent, status_fn=_print_extent_status),
    Mode(25, True, "cursor_visible", queryable=True, peripheral="cursor"),
    Mode(42, True, "national_charset_mode", queryable=True),
    Mode(45, True, "reverse_wraparound", queryable=True),
    Mode(47, True, apply_fn=_alt_screen, status_fn=_alt_screen_status),
    Mode(66, True, "numeric_keypad", invert=True, queryable=True),
    Mode(67, True, "backarrow_key_sends_bs", queryable=True),
    Mode(69, True, "left_right_margin_mode", queryable=True, apply_fn=_declrmm),  # DECLRMM
    Mode(95, True, "no_clear_column_mode", queryable=True),
    Mode(1000, True, "mouse_tracking", queryable=True, peripheral="mouse"),
    Mode(1004, True, "focus_reporting", queryable=True),
    Mode(1002, True, apply_fn=_mouse_button_tracking, status_fn=_mouse_button_status, peripheral="mouse"),
    Mode(1003, True, apply_fn=_mouse_any_tracking, status_fn=_mouse_any_status, peripheral="mouse"),
    Mode(1005, True, "mouse_utf8_mode", queryable=True),
    Mode(1006, True, "mouse_sgr_mode", queryable=True, peripheral="mouse"),
    Mode(1007, True, "alternate_scroll_mode", queryable=True, peripheral="mouse"),
    Mode(1015, True, "urxvt_mouse", queryable=True),
    Mode(1034, True, "eight_bit_input", queryable=True),
    Mode(1035, True, "special_modifiers", queryable=True),
    Mode(1036, True, "meta_sends_escape", queryable=True),
    Mode(1037, True, "delete_sends_del", queryable=True),
    Mode(1039, True, "alt_sends_escape", queryable=True),
    Mode(1047, True, apply_fn=_alt_screen, status_fn=_alt_screen_status),
    Mode(1048, True, apply_fn=_save_restore_cursor),
    Mode(1049, True, apply_fn=_alt_screen_and_cursor, status_fn=_alt_screen_status),
    # Extended modes with implemented board or frontend behaviour.
    Mode(40, True, "allow_column_mode", queryable=True),  # permit DECCOLM 80<->132
    Mode(1045, True, "extended_reverse_wraparound", queryable=True),
    Mode(1046, True, "allow_alt_screen", queryable=True, apply_fn=_allow_alt_screen),
    Mode(2004, True, "bracketed_paste", queryable=True),
    Mode(2026, True, "synchronized_output", queryable=True, peripheral="sync"),
    Mode(
        2027,
        True,
        "grapheme_clustering",
        queryable=True,
        apply_fn=_grapheme_clustering,
        peripheral="grapheme",
    ),
    Mode(
        8840,
        True,
        "ambiguous_width_double",
        queryable=True,
        apply_fn=_ambiguous_width,
        peripheral="width",
    ),
]


class ModeDevice(Device):
    """Owns terminal mode state and applies mode operations via the mode table."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self._set_defaults()
        # Edge-trigger caches for peripheral present events (None = not yet emitted).
        self._last_mouse_mode: tuple[str, bool] | None = None
        self._last_cursor_visible: bool | None = None
        self._last_cursor_blinking: bool | None = None
        self._last_reverse_screen: bool | None = None
        self._last_sync: bool | None = None
        self._last_ambiguous_width: int | None = None
        self._last_grapheme_clustering: bool | None = None
        unsupported = board.model.unsupported_modes
        self._modes = {mode.key: mode for mode in MODE_SPECS if mode.key not in unsupported}
        # Runtime destination policy. Only fixed DECRQM states live here:
        # 0=unsupported, 3=permanently set, 4=permanently reset.
        self._runtime_mode_status: dict[tuple[bool, int], int] = {}
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
        # Reserved defaults for modes outside the implemented repertoire.
        # DECSET ignores these until the corresponding behaviour is added.
        self.keyboard_action_mode = False
        self.allow_column_mode = False
        self.national_charset_mode = False
        self.margin_bell = False
        self.reverse_wraparound = False
        self.extended_reverse_wraparound = False
        self.no_clear_column_mode = False
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
        self.ambiguous_width_double = self.board.width_policy.ambiguous_width == 2
        self.color_scheme_updates = False
        self.scroll_on_output = False
        self.scroll_on_keypress = False
        self.eight_bit_input = False
        self.special_modifiers = True  # xterm default: Alt/NumLock modifiers active
        self.delete_sends_del = False
        self.keep_selection = False
        self.select_to_clipboard = False
        self.reuse_clipboard = False
        self.sixel_private_registers = True  # xterm default: per-sixel private colour registers
        self.application_escape = False
        self.mousewheel_to_arrows = False
        self.sixel_cursor_right = False

    def reset(self, hard: bool = True) -> None:
        """Reset modes. hard restores every flag (RIS); soft is the DECSTR subset."""
        if hard:
            self._set_defaults()
            fixed_grapheme = self._runtime_mode_status.get((True, 2027))
            self.grapheme_clustering = fixed_grapheme == 3
            self.board.blitter.set_grapheme_clustering(self.grapheme_clustering)
            self.board.restore_width_policy()
        else:
            # DECSTR soft reset — the widely-agreed subset (SGR is reset by the style device).
            self.insert_mode = False
            self.origin_mode = False
            self.cursor_visible = True
        # A reset can turn peripheral state off (e.g. RIS with mouse on); tell the terminal (chrome).
        for peripheral in ("mouse", "cursor", "cursor_blink", "reverse", "sync", "width", "grapheme"):
            self._emit_peripheral(peripheral)

    # --- dispatch --- #

    def apply_mode_operation(self, operation: Operation) -> None:
        params, set_mode, private = operation.args
        modes = self.set_private_modes if private else self.set_ansi_modes
        modes(params, set_mode)

    def enter_application_keypad(self, operation: Operation) -> None:
        self.application_keypad = True
        self.numeric_keypad = False

    def enter_numeric_keypad(self, operation: Operation) -> None:
        self.application_keypad = False
        self.numeric_keypad = True

    # --- applying modes --- #

    def _apply(self, private: bool, param: int | None, value: bool) -> None:
        if param is None:
            return
        key = (private, param)
        mode = self._modes.get(key)
        if mode is not None and self._runtime_mode_status.get(key) not in (0, 3, 4):
            mode.apply(self, value)
            if mode.peripheral is not None:
                self._emit_peripheral(mode.peripheral)

    def _mouse_mode(self) -> tuple[str, bool]:
        """Derive the requested mouse-tracking mode from the flags (any > button > basic > off)."""
        if self.mouse_any_tracking:
            mode = "any"
        elif self.mouse_button_tracking:
            mode = "button"
        elif self.mouse_tracking or (self.alternate_scroll_mode and self.board.blitter.in_alt_screen):
            mode = "basic"
        else:
            mode = "off"
        return mode, self.mouse_sgr_mode

    def _emit_peripheral(self, peripheral: str) -> None:
        """Present a peripheral event, edge-triggered on the derived state changing."""
        if peripheral == "mouse":
            state = self._mouse_mode()
            if state != self._last_mouse_mode:
                self._last_mouse_mode = state
                self.board.present(MouseModeChanged(*state))
        elif peripheral == "cursor":
            if self.cursor_visible != self._last_cursor_visible:
                self._last_cursor_visible = self.cursor_visible
                self.board.present(CursorVisibilityChanged(self.cursor_visible))
        elif peripheral == "cursor_blink":
            if self.cursor_blinking != self._last_cursor_blinking:
                self._last_cursor_blinking = self.cursor_blinking
                self.board.present(CursorBlinkChanged(self.cursor_blinking))
        elif peripheral == "reverse":
            if self.reverse_screen != self._last_reverse_screen:
                self._last_reverse_screen = self.reverse_screen
                self.board.present(ReverseScreenChanged(self.reverse_screen))
        elif peripheral == "sync":
            if self.synchronized_output != self._last_sync:
                self._last_sync = self.synchronized_output
                self.board.present(SyncOutputChanged(self.synchronized_output))
        elif peripheral == "width":
            if (True, 8840) not in self._modes:
                return
            width = 2 if self.ambiguous_width_double else 1
            if width != self._last_ambiguous_width:
                self._last_ambiguous_width = width
                self.board.present(AmbiguousWidthChanged(width))
        elif peripheral == "grapheme":
            if self.grapheme_clustering != self._last_grapheme_clustering:
                self._last_grapheme_clustering = self.grapheme_clustering
                self.board.present(GraphemeClusteringChanged(self.grapheme_clustering))

    def set_cursor_blinking(self, enabled: bool) -> None:
        """Set cursor blink state and notify the attached terminal on an edge."""
        self.cursor_blinking = enabled
        self._emit_peripheral("cursor_blink")

    def set_grapheme_capability(self, capability: str) -> None:
        """Apply the destination's mode-2027 policy without changing the model repertoire."""
        key = (True, 2027)
        mode = self._modes.get(key)
        if mode is None:
            return

        status = {
            "unsupported": 0,
            "reset": 2,
            "set": 1,
            "permanently-reset": 4,
            "permanently-set": 3,
        }[capability]
        if status in (0, 3, 4):
            self._runtime_mode_status[key] = status
        else:
            self._runtime_mode_status.pop(key, None)

        if status in (0, 4):
            mode.apply(self, False)
        elif status == 3:
            mode.apply(self, True)

        # A newly attached/reprobed destination must receive the current state
        # even when the logical mode itself did not change.
        self._last_grapheme_clustering = None
        self._emit_peripheral("grapheme")

    def set_ansi_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            self._apply(False, param, set_mode)

    def set_private_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        for param in params:
            self._apply(True, param, set_mode)

    def set_mode(self, mode: int, value: bool = True, private: bool = False) -> None:
        """Set a single terminal mode."""
        self._apply(private, mode, value)

    def recognizes(self, private: bool, mode: int) -> bool:
        """Whether this model implements a mode."""
        return (private, mode) in self._modes

    def clear_mode(self, mode: int, private: bool = False) -> None:
        """Clear a single terminal mode."""
        self._apply(private, mode, False)

    # --- DECRQM status --- #

    def get_private_mode_status(self, mode: int) -> int:
        key = (True, mode)
        if key in self._runtime_mode_status:
            return self._runtime_mode_status[key]
        entry = self._modes.get(key)
        return entry.status(self) if entry is not None else 0

    def get_ansi_mode_status(self, mode: int) -> int:
        entry = self._modes.get((False, mode))
        return entry.status(self) if entry is not None else 0
