"""Declarative ANSI/DEC modes resolved through model capability profiles."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .. import mode_profiles as mp
from ..operations import Operation
from ..present import (
    AmbiguousWidthChanged,
    CursorBlinkChanged,
    CursorVisibilityChanged,
    GraphemeClusteringChanged,
    KeyboardLockChanged,
    MouseCaptureChanged,
    ReverseScreenChanged,
    SyncOutputChanged,
)
from .base import Device

if TYPE_CHECKING:
    from .board import Board


class ModeEffect(Enum):
    """Derived frontend state that may need reconciliation after a mode change."""

    MOUSE_CAPTURE = "mouse-capture"
    CURSOR = "cursor"
    CURSOR_BLINK = "cursor-blink"
    REVERSE = "reverse"
    SYNC = "sync"
    WIDTH = "width"
    GRAPHEME = "grapheme"
    KEYBOARD_LOCK = "keyboard-lock"


class MouseProtocol(Enum):
    """Mutually exclusive application mouse protocols."""

    OFF = "off"
    X10 = "x10"
    NORMAL = "normal"
    BUTTON = "button"
    ANY = "any"
    LOCATOR = "locator"


class MouseEncoding(Enum):
    """Mutually exclusive encodings for xterm-family mouse reports."""

    LEGACY = "legacy"
    UTF8 = "utf8"
    SGR = "sgr"
    URXVT = "urxvt"


DefaultValue = bool | Callable[["ModeDevice"], bool]


@dataclass(frozen=True)
class ModeSpec:
    """One semantic capability and its numbered representation."""

    capability: str
    number: int
    private: bool
    attr: str | None = None  # device flag this mode drives, if any
    default: DefaultValue = False  # underlying attr value at power-on
    invert: bool = False  # "set" stores the negation (modes 12, 66)
    queryable: bool = False  # DECRQM reports this mode's state
    apply_fn: Callable[[ModeDevice, bool], None] | None = None  # side effect
    status_fn: Callable[[ModeDevice], int] | None = None  # custom DECRQM status
    group: str | None = None
    group_value: MouseProtocol | MouseEncoding | None = None
    effects: frozenset[ModeEffect] = frozenset()
    save_fn: Callable[[ModeDevice], None] | None = None
    restore_fn: Callable[[ModeDevice], None] | None = None

    @property
    def key(self) -> tuple[bool, int]:
        return (self.private, self.number)

    def apply(self, device: ModeDevice, value: bool) -> None:
        if self.group is not None:
            device._set_group_member(self.group, self.group_value, value)
        elif self.attr is not None:
            setattr(device, self.attr, (not value) if self.invert else value)
        if self.apply_fn is not None:
            self.apply_fn(device, value)

    def status(self, device: ModeDevice) -> int:
        """DECRQM status: 1 = set, 2 = reset, 0 = not recognised."""
        if self.status_fn is not None:
            return self.status_fn(device)
        if self.group is not None:
            return 1 if getattr(device, self.group) == self.group_value else 2
        if self.queryable and self.attr is not None:
            state = getattr(device, self.attr)
            return 1 if ((not state) if self.invert else state) else 2
        return 0


# --- side effects for modes that do more than flip a flag --- #


def _dec_deccolm(device: ModeDevice, value: bool) -> None:
    device.board.blitter.set_column_mode(132 if value else 80)


def _xterm_deccolm(device: ModeDevice, value: bool) -> None:
    # xterm ignores DECCOLM unless mode 40 permits it — reset strings carry ?3l,
    # and honouring it ungated shrinks any wider terminal to 80 columns.
    if device.allow_column_mode:
        device.board.blitter.set_column_mode(132 if value else 80)


def _clear_and_home(device: ModeDevice) -> None:
    device.board.blitter.clear_screen(2)
    device.board.cursor.set_position(0, 0)


def _tmux_deccolm(device: ModeDevice, value: bool) -> None:
    _clear_and_home(device)


def _tmux_column_status(device: ModeDevice) -> int:
    return 4  # tmux recognises DECCOLM but reports it permanently reset


def _kitty_deccolm(device: ModeDevice, value: bool) -> None:
    if value:
        _clear_and_home(device)


def _alt_screen(device: ModeDevice, value: bool) -> None:
    if device.allow_alt_screen:
        device.board.blitter.switch_screen(value)


def _save_restore_cursor(device: ModeDevice, value: bool) -> None:
    if not device.allow_alt_screen:
        return
    if value:
        device.board.cursor.save()
    else:
        device.board.cursor.restore()


def _save_cursor_mode(device: ModeDevice) -> None:
    device.board.cursor.save()


def _restore_cursor_mode(device: ModeDevice) -> None:
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


def _allow_alt_screen(device: ModeDevice, value: bool) -> None:
    if not value:
        device.board.blitter.switch_screen(False)


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


def _ignore_null(device: ModeDevice, value: bool) -> None:
    device.board.printer.set_ignore_null(value)


def _ignore_null_status(device: ModeDevice) -> int:
    return 1 if device.board.printer.configuration.ignore_null else 2


def _conceal_answerback(device: ModeDevice, value: bool) -> None:
    device.board.set_answerback_concealed(value)


def _conceal_answerback_status(device: ModeDevice) -> int:
    return 1 if device.board.answerback_concealed else 2


def _inband_resize(device: ModeDevice, value: bool) -> None:
    if value:
        device.board.report_resize()


def _margin_bell(device: ModeDevice, value: bool) -> None:
    device.board.reset_margin_bell()


def _ambiguous_width_default(device: ModeDevice) -> bool:
    return device.board.width_policy.ambiguous_width == 2


_MOUSE_EFFECT = frozenset({ModeEffect.MOUSE_CAPTURE})

# Every implemented semantic capability. Models select these by capability ID.
MODE_SPECS: tuple[ModeSpec, ...] = (
    # ANSI modes (autowrap and cursor visibility are DEC *private* 7/25, not ANSI)
    ModeSpec(
        mp.ANSI_KEYBOARD_ACTION,
        2,
        False,
        "keyboard_locked",
        queryable=True,
        effects=frozenset({ModeEffect.KEYBOARD_LOCK}),
    ),
    ModeSpec(mp.ANSI_INSERT, 4, False, "insert_mode", queryable=True),
    ModeSpec(mp.ANSI_SEND_RECEIVE, 12, False, "local_echo", invert=True, queryable=True),
    ModeSpec(mp.ANSI_NEWLINE, 20, False, "linefeed_newline_mode", queryable=True),
    # DEC private modes
    ModeSpec(mp.DEC_CURSOR_APPLICATION, 1, True, "cursor_application_mode", queryable=True),
    ModeSpec(mp.DEC_COLUMN_MODE, 3, True, apply_fn=_dec_deccolm, status_fn=_column_status),
    ModeSpec(mp.XTERM_COLUMN_MODE, 3, True, apply_fn=_xterm_deccolm, status_fn=_column_status),
    ModeSpec(mp.TMUX_COLUMN_MODE, 3, True, apply_fn=_tmux_deccolm, status_fn=_tmux_column_status),
    ModeSpec(
        mp.KITTY_COLUMN_MODE,
        3,
        True,
        "column_mode",
        queryable=True,
        apply_fn=_kitty_deccolm,
    ),
    ModeSpec(
        mp.DEC_REVERSE_SCREEN,
        5,
        True,
        "reverse_screen",
        queryable=True,
        effects=frozenset({ModeEffect.REVERSE}),
    ),
    ModeSpec(mp.DEC_ORIGIN, 6, True, "origin_mode", queryable=True),
    ModeSpec(mp.DEC_AUTOWRAP, 7, True, "auto_wrap", default=True, queryable=True),
    ModeSpec(
        mp.XTERM_MOUSE_X10,
        9,
        True,
        queryable=True,
        group="mouse_protocol",
        group_value=MouseProtocol.X10,
        effects=_MOUSE_EFFECT,
    ),
    ModeSpec(
        mp.XTERM_CURSOR_BLINK,
        12,
        True,
        "cursor_blinking",
        queryable=True,
        effects=frozenset({ModeEffect.CURSOR_BLINK}),
    ),
    ModeSpec(mp.DEC_PRINT_FORM_FEED, 18, True, apply_fn=_print_form_feed, status_fn=_print_form_feed_status),
    ModeSpec(mp.DEC_PRINT_EXTENT, 19, True, apply_fn=_print_extent, status_fn=_print_extent_status),
    ModeSpec(
        mp.DEC_CURSOR_VISIBLE,
        25,
        True,
        "cursor_visible",
        default=True,
        queryable=True,
        effects=frozenset({ModeEffect.CURSOR}),
    ),
    ModeSpec(mp.DEC_NATIONAL_CHARSET, 42, True, "national_charset_mode", queryable=True),
    ModeSpec(mp.XTERM_MARGIN_BELL, 44, True, "margin_bell", queryable=True, apply_fn=_margin_bell),
    ModeSpec(mp.XTERM_REVERSE_WRAP, 45, True, "reverse_wraparound", queryable=True),
    ModeSpec(
        mp.XTERM_ALT_SCREEN_47,
        47,
        True,
        apply_fn=_alt_screen,
        status_fn=_alt_screen_status,
        effects=_MOUSE_EFFECT,
    ),
    ModeSpec(mp.DEC_NUMERIC_KEYPAD, 66, True, "numeric_keypad", default=True, invert=True, queryable=True),
    ModeSpec(mp.DEC_BACKARROW, 67, True, "backarrow_key_sends_bs", queryable=True),
    ModeSpec(
        mp.DEC_LEFT_RIGHT_MARGINS,
        69,
        True,
        "left_right_margin_mode",
        queryable=True,
        apply_fn=_declrmm,
    ),
    ModeSpec(mp.DEC_NO_CLEAR_COLUMN, 95, True, "no_clear_column_mode", queryable=True),
    ModeSpec(mp.DEC_AUTO_ANSWERBACK, 100, True, "auto_answerback", queryable=True),
    ModeSpec(
        mp.DEC_CONCEAL_ANSWERBACK,
        101,
        True,
        apply_fn=_conceal_answerback,
        status_fn=_conceal_answerback_status,
    ),
    ModeSpec(
        mp.DEC_IGNORE_NULL,
        102,
        True,
        "ignore_null",
        queryable=True,
        apply_fn=_ignore_null,
        status_fn=_ignore_null_status,
    ),
    ModeSpec(
        mp.XTERM_MOUSE_NORMAL,
        1000,
        True,
        queryable=True,
        group="mouse_protocol",
        group_value=MouseProtocol.NORMAL,
        effects=_MOUSE_EFFECT,
    ),
    ModeSpec(mp.XTERM_FOCUS, 1004, True, "focus_reporting", queryable=True),
    ModeSpec(
        mp.XTERM_MOUSE_BUTTON,
        1002,
        True,
        queryable=True,
        group="mouse_protocol",
        group_value=MouseProtocol.BUTTON,
        effects=_MOUSE_EFFECT,
    ),
    ModeSpec(
        mp.XTERM_MOUSE_ANY,
        1003,
        True,
        queryable=True,
        group="mouse_protocol",
        group_value=MouseProtocol.ANY,
        effects=_MOUSE_EFFECT,
    ),
    ModeSpec(
        mp.XTERM_MOUSE_UTF8,
        1005,
        True,
        queryable=True,
        group="mouse_encoding",
        group_value=MouseEncoding.UTF8,
    ),
    ModeSpec(
        mp.XTERM_MOUSE_SGR,
        1006,
        True,
        queryable=True,
        group="mouse_encoding",
        group_value=MouseEncoding.SGR,
    ),
    ModeSpec(
        mp.XTERM_ALTERNATE_SCROLL,
        1007,
        True,
        "alternate_scroll_mode",
        queryable=True,
        effects=_MOUSE_EFFECT,
    ),
    ModeSpec(
        mp.URXVT_MOUSE,
        1015,
        True,
        queryable=True,
        group="mouse_encoding",
        group_value=MouseEncoding.URXVT,
    ),
    ModeSpec(mp.XTERM_EIGHT_BIT_INPUT, 1034, True, "eight_bit_input", queryable=True),
    ModeSpec(
        mp.XTERM_SPECIAL_MODIFIERS,
        1035,
        True,
        "special_modifiers",
        default=True,
        queryable=True,
    ),
    ModeSpec(mp.XTERM_META_ESCAPE, 1036, True, "meta_sends_escape", queryable=True),
    ModeSpec(mp.XTERM_DELETE, 1037, True, "delete_sends_del", queryable=True),
    ModeSpec(mp.XTERM_ALT_ESCAPE, 1039, True, "alt_sends_escape", queryable=True),
    ModeSpec(mp.XTERM_BELL_URGENT, 1042, True, "bell_urgent", queryable=True),
    ModeSpec(mp.XTERM_BELL_RAISE, 1043, True, "bell_raise", queryable=True),
    ModeSpec(
        mp.XTERM_ALT_SCREEN_1047,
        1047,
        True,
        apply_fn=_alt_screen,
        status_fn=_alt_screen_status,
        effects=_MOUSE_EFFECT,
    ),
    ModeSpec(
        mp.XTERM_SAVE_CURSOR_1048,
        1048,
        True,
        apply_fn=_save_restore_cursor,
        save_fn=_save_cursor_mode,
        restore_fn=_restore_cursor_mode,
    ),
    ModeSpec(
        mp.XTERM_ALT_SCREEN_1049,
        1049,
        True,
        apply_fn=_alt_screen_and_cursor,
        status_fn=_alt_screen_status,
        effects=_MOUSE_EFFECT,
    ),
    # Extended modes with implemented board or frontend behaviour.
    ModeSpec(mp.XTERM_ALLOW_COLUMN, 40, True, "allow_column_mode", queryable=True),
    ModeSpec(mp.XTERM_EXTENDED_REVERSE_WRAP, 1045, True, "extended_reverse_wraparound", queryable=True),
    ModeSpec(
        mp.XTERM_ALLOW_ALT_SCREEN,
        1046,
        True,
        "allow_alt_screen",
        default=True,
        queryable=True,
        apply_fn=_allow_alt_screen,
        effects=_MOUSE_EFFECT,
    ),
    ModeSpec(mp.XTERM_BRACKETED_PASTE, 2004, True, "bracketed_paste", queryable=True),
    ModeSpec(
        mp.INBAND_RESIZE,
        2048,
        True,
        "inband_resize",
        queryable=True,
        apply_fn=_inband_resize,
    ),
    ModeSpec(
        mp.XTERM_SYNC_OUTPUT,
        2026,
        True,
        "synchronized_output",
        queryable=True,
        effects=frozenset({ModeEffect.SYNC}),
    ),
    ModeSpec(
        mp.UNICODE_GRAPHEME_CLUSTERING,
        2027,
        True,
        "grapheme_clustering",
        queryable=True,
        apply_fn=_grapheme_clustering,
        effects=frozenset({ModeEffect.GRAPHEME}),
    ),
    ModeSpec(
        mp.UNICODE_AMBIGUOUS_WIDTH,
        8840,
        True,
        "ambiguous_width_double",
        default=_ambiguous_width_default,
        queryable=True,
        apply_fn=_ambiguous_width,
        effects=frozenset({ModeEffect.WIDTH}),
    ),
)


MODE_BY_CAPABILITY = {mode.capability: mode for mode in MODE_SPECS}
if len(MODE_BY_CAPABILITY) != len(MODE_SPECS):
    raise RuntimeError("duplicate mode capability ID")
if frozenset(MODE_BY_CAPABILITY) != mp.ALL_MODE_CAPABILITIES:
    raise RuntimeError("mode capability profile and implementation registry differ")
if any((mode.save_fn is None) != (mode.restore_fn is None) for mode in MODE_SPECS):
    raise RuntimeError("mode save and restore hooks must be declared together")


def resolve_mode_specs(
    capabilities: frozenset[str],
    unsupported: frozenset[tuple[bool, int]] = frozenset(),
    *,
    specs: tuple[ModeSpec, ...] = MODE_SPECS,
) -> dict[tuple[bool, int], ModeSpec]:
    """Resolve semantic capabilities to one collision-free numbered repertoire."""
    registry = {mode.capability: mode for mode in specs}
    if len(registry) != len(specs):
        raise ValueError("duplicate mode capability ID")
    unknown = capabilities.difference(registry)
    if unknown:
        raise ValueError(f"unknown mode capabilities: {', '.join(sorted(unknown))}")
    resolved: dict[tuple[bool, int], ModeSpec] = {}
    for spec in specs:
        if spec.capability not in capabilities or spec.key in unsupported:
            continue
        previous = resolved.get(spec.key)
        if previous is not None:
            raise ValueError(f"mode {spec.key} is claimed by both {previous.capability!r} and {spec.capability!r}")
        resolved[spec.key] = spec
    return resolved


class ModeDevice(Device):
    """Owns terminal mode state and applies mode operations via the mode table."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self._modes = resolve_mode_specs(board.model.mode_capabilities, board.model.unsupported_modes)
        self._runtime_mode_status: dict[tuple[bool, int], int] = {}
        # None marks an action-mode whose save/restore hooks own the snapshot.
        self._saved_private_modes: dict[int, bool | None] = {}
        self._batch_depth = 0
        self._pending_effects: set[ModeEffect] = set()
        # Edge-trigger caches for frontend present events (None = not yet emitted).
        self._last_mouse_capture: str | None = None
        self._last_cursor_visible: bool | None = None
        self._last_cursor_blinking: bool | None = None
        self._last_reverse_screen: bool | None = None
        self._last_sync: bool | None = None
        self._last_ambiguous_width: int | None = None
        self._last_grapheme_clustering: bool | None = None
        self._last_keyboard_locked: bool | None = None
        self._set_defaults()
        self.handlers = {
            "SM": self.apply_mode_operation,
            "RM": self.apply_mode_operation,
            "DECSET": self.apply_mode_operation,
            "DECRST": self.apply_mode_operation,
            "XTSAVE": self.save_private_mode_operation,
            "XTRESTORE": self.restore_private_mode_operation,
            "DECKPAM": self.enter_application_keypad,
            "DECKPNM": self.enter_numeric_keypad,
        }

    def _set_defaults(self) -> None:
        """Restore declared mode defaults and the non-mode keypad registers."""
        self.mouse_protocol = MouseProtocol.OFF
        self.mouse_encoding = MouseEncoding.LEGACY
        initialized: set[str] = set()
        for spec in MODE_SPECS:
            if spec.attr is None or spec.attr in initialized:
                continue
            default = spec.default(self) if callable(spec.default) else spec.default
            setattr(self, spec.attr, default)
            initialized.add(spec.attr)

        # DECKPAM/DECKPNM are escape controls, not SM/RM modes.
        self.application_keypad = False
        # DECARM remains a hardware register until repeat events carry enough metadata.
        self.auto_repeat = True

    def reset(self, hard: bool = True, *, reconcile: bool = True) -> None:
        """Reset modes. hard restores every flag (RIS); soft is the DECSTR subset."""
        if hard:
            self._saved_private_modes.clear()
            self._set_defaults()
            if hasattr(self.board, "mouse"):
                self.board.mouse._disable_locator_state()
            fixed_grapheme = self._runtime_mode_status.get((True, 2027))
            self.grapheme_clustering = fixed_grapheme == 3
            self.board.blitter.set_grapheme_clustering(self.grapheme_clustering)
            self.board.restore_width_policy()
        else:
            # DECSTR soft reset — the widely-agreed subset (SGR is reset by the style device).
            self.insert_mode = False
            self.origin_mode = False
            self.cursor_visible = True
            self.ignore_null = False
            if hasattr(self, "keyboard_locked"):
                self.keyboard_locked = False
        if reconcile:
            self.reconcile_all()

    # --- dispatch --- #

    def apply_mode_operation(self, operation: Operation) -> None:
        params, set_mode, private = operation.args
        modes = self.set_private_modes if private else self.set_ansi_modes
        modes(params, set_mode)

    def save_private_mode_operation(self, operation: Operation) -> None:
        self.save_private_modes(operation.args[0])

    def restore_private_mode_operation(self, operation: Operation) -> None:
        self.restore_private_modes(operation.args[0])

    def enter_application_keypad(self, operation: Operation) -> None:
        self.application_keypad = True
        self.numeric_keypad = False

    def enter_numeric_keypad(self, operation: Operation) -> None:
        self.application_keypad = False
        self.numeric_keypad = True

    # --- applying modes --- #

    def _set_group(self, group: str, value: MouseProtocol | MouseEncoding | None) -> None:
        if group == "mouse_protocol":
            protocol = MouseProtocol.OFF if value is None else value
            if protocol is not MouseProtocol.LOCATOR and hasattr(self.board, "mouse"):
                self.board.mouse._disable_locator_state()
            self.mouse_protocol = protocol
        elif group == "mouse_encoding":
            self.mouse_encoding = MouseEncoding.LEGACY if value is None else value
        else:
            raise ValueError(f"unknown exclusive mode group {group!r}")

    def _set_group_member(
        self,
        group: str,
        member: MouseProtocol | MouseEncoding | None,
        enabled: bool,
    ) -> None:
        """Set a group member, or clear it only when that member is selected."""
        if enabled:
            self._set_group(group, member)
        elif getattr(self, group) is member:
            self._set_group(group, None)

    def select_mouse_protocol(self, protocol: MouseProtocol) -> None:
        """Select a protocol from DEC locator or a compatibility caller."""
        self._set_group("mouse_protocol", protocol)
        self.reconcile(ModeEffect.MOUSE_CAPTURE)

    def clear_locator_protocol(self) -> None:
        """Turn tracking off only when DEC locator currently owns the protocol."""
        if self.mouse_protocol is MouseProtocol.LOCATOR:
            self.mouse_protocol = MouseProtocol.OFF
            self.reconcile(ModeEffect.MOUSE_CAPTURE)

    def _apply(self, private: bool, param: int | None, value: bool) -> frozenset[ModeEffect]:
        if param is None:
            return frozenset()
        key = (private, param)
        mode = self._modes.get(key)
        if mode is not None and self._runtime_mode_status.get(key) not in (0, 3, 4):
            mode.apply(self, value)
            return mode.effects
        return frozenset()

    def _apply_values(self, private: bool, values: Iterable[tuple[int | None, bool]]) -> None:
        self._batch_depth += 1
        try:
            for param, value in values:
                self._pending_effects.update(self._apply(private, param, value))
        finally:
            self._batch_depth -= 1
        if self._batch_depth == 0 and self._pending_effects:
            pending = frozenset(self._pending_effects)
            self._pending_effects.clear()
            self.reconcile(*pending)

    def _apply_many(self, private: bool, params: tuple[int | None, ...], value: bool) -> None:
        self._apply_values(private, ((param, value) for param in params))

    def _mouse_capture(self) -> str:
        """Derive the physical events the attached frontend must capture."""
        protocol = self.mouse_protocol
        if protocol in (MouseProtocol.ANY, MouseProtocol.LOCATOR):
            return "any"
        if protocol is MouseProtocol.BUTTON:
            return "button"
        if protocol in (MouseProtocol.X10, MouseProtocol.NORMAL):
            return "basic"
        if self.alternate_scroll_mode and self.board.blitter.in_alt_screen:
            return "basic"
        return "off"

    def reconcile(self, *effects: ModeEffect, force: bool = False) -> None:
        """Reconcile typed derived frontend state, batching during mode lists."""
        if self._batch_depth:
            self._pending_effects.update(effects)
            return
        requested = frozenset(effects)
        for effect in ModeEffect:
            if effect in requested:
                self._emit_effect(effect, force=force)

    def reconcile_all(self, *, force: bool = False) -> None:
        """Reconcile every frontend-facing mode effect."""
        self.reconcile(*ModeEffect, force=force)

    def _emit_effect(self, effect: ModeEffect, *, force: bool = False) -> None:
        if effect is ModeEffect.MOUSE_CAPTURE:
            state = self._mouse_capture()
            if force or state != self._last_mouse_capture:
                self._last_mouse_capture = state
                self.board.present(MouseCaptureChanged(state))
        elif effect is ModeEffect.CURSOR:
            if force or self.cursor_visible != self._last_cursor_visible:
                self._last_cursor_visible = self.cursor_visible
                self.board.present(CursorVisibilityChanged(self.cursor_visible))
        elif effect is ModeEffect.CURSOR_BLINK:
            if force or self.cursor_blinking != self._last_cursor_blinking:
                self._last_cursor_blinking = self.cursor_blinking
                self.board.present(CursorBlinkChanged(self.cursor_blinking))
        elif effect is ModeEffect.REVERSE:
            if force or self.reverse_screen != self._last_reverse_screen:
                self._last_reverse_screen = self.reverse_screen
                self.board.present(ReverseScreenChanged(self.reverse_screen))
        elif effect is ModeEffect.SYNC:
            if force or self.synchronized_output != self._last_sync:
                self._last_sync = self.synchronized_output
                self.board.present(SyncOutputChanged(self.synchronized_output))
        elif effect is ModeEffect.WIDTH:
            if (True, 8840) not in self._modes:
                return
            width = 2 if self.ambiguous_width_double else 1
            if force or width != self._last_ambiguous_width:
                self._last_ambiguous_width = width
                self.board.present(AmbiguousWidthChanged(width))
        elif effect is ModeEffect.GRAPHEME:
            if force or self.grapheme_clustering != self._last_grapheme_clustering:
                self._last_grapheme_clustering = self.grapheme_clustering
                self.board.present(GraphemeClusteringChanged(self.grapheme_clustering))
        elif effect is ModeEffect.KEYBOARD_LOCK:
            if force or self.keyboard_locked != self._last_keyboard_locked:
                self._last_keyboard_locked = self.keyboard_locked
                self.board.present(KeyboardLockChanged(self.keyboard_locked))

    def set_cursor_blinking(self, enabled: bool) -> None:
        """Set cursor blink state and notify the attached terminal on an edge."""
        self.cursor_blinking = enabled
        self.reconcile(ModeEffect.CURSOR_BLINK)

    # Compatibility properties for callers that used the former mouse booleans.

    @property
    def mouse_tracking(self) -> bool:
        return self.mouse_protocol in {
            MouseProtocol.X10,
            MouseProtocol.NORMAL,
            MouseProtocol.BUTTON,
            MouseProtocol.ANY,
        }

    @mouse_tracking.setter
    def mouse_tracking(self, enabled: bool) -> None:
        self.select_mouse_protocol(MouseProtocol.NORMAL if enabled else MouseProtocol.OFF)

    @property
    def mouse_button_tracking(self) -> bool:
        return self.mouse_protocol is MouseProtocol.BUTTON

    @mouse_button_tracking.setter
    def mouse_button_tracking(self, enabled: bool) -> None:
        self._set_group_member("mouse_protocol", MouseProtocol.BUTTON, enabled)
        self.reconcile(ModeEffect.MOUSE_CAPTURE)

    @property
    def mouse_any_tracking(self) -> bool:
        return self.mouse_protocol is MouseProtocol.ANY

    @mouse_any_tracking.setter
    def mouse_any_tracking(self, enabled: bool) -> None:
        self._set_group_member("mouse_protocol", MouseProtocol.ANY, enabled)
        self.reconcile(ModeEffect.MOUSE_CAPTURE)

    @property
    def mouse_utf8_mode(self) -> bool:
        return self.mouse_encoding is MouseEncoding.UTF8

    @mouse_utf8_mode.setter
    def mouse_utf8_mode(self, enabled: bool) -> None:
        self._set_group_member("mouse_encoding", MouseEncoding.UTF8, enabled)

    @property
    def mouse_sgr_mode(self) -> bool:
        return self.mouse_encoding is MouseEncoding.SGR

    @mouse_sgr_mode.setter
    def mouse_sgr_mode(self, enabled: bool) -> None:
        self._set_group_member("mouse_encoding", MouseEncoding.SGR, enabled)

    @property
    def urxvt_mouse(self) -> bool:
        return self.mouse_encoding is MouseEncoding.URXVT

    @urxvt_mouse.setter
    def urxvt_mouse(self, enabled: bool) -> None:
        self._set_group_member("mouse_encoding", MouseEncoding.URXVT, enabled)

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
        self.reconcile(ModeEffect.GRAPHEME, force=True)

    def set_ansi_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        self._apply_many(False, params, set_mode)

    def set_private_modes(self, params: tuple[int | None, ...], set_mode: bool) -> None:
        self._apply_many(True, params, set_mode)

    def save_private_modes(self, params: tuple[int | None, ...]) -> None:
        """XTSAVE — cache the current value of each recognised private mode."""
        for param in params:
            if not isinstance(param, int):
                continue
            entry = self._modes.get((True, param))
            if entry is None or self._runtime_mode_status.get((True, param)) == 0:
                continue
            if entry.save_fn is not None:
                entry.save_fn(self)
                self._saved_private_modes[param] = None
                continue
            status = self.get_private_mode_status(param)
            if status in (1, 2, 3, 4):
                self._saved_private_modes[param] = status in (1, 3)

    def restore_private_modes(self, params: tuple[int | None, ...]) -> None:
        """XTRESTORE — restore only listed modes that have a cached value."""
        saved = self._saved_private_modes

        def saved_values() -> Iterable[tuple[int, bool]]:
            for param in params:
                if not isinstance(param, int) or param not in saved:
                    continue
                value = saved[param]
                if value is None:
                    restore = self._modes[(True, param)].restore_fn
                    assert restore is not None
                    restore(self)
                else:
                    yield param, value

        self._apply_values(True, saved_values())

    def set_mode(self, mode: int, value: bool = True, private: bool = False) -> None:
        """Set a single terminal mode."""
        self._apply_many(private, (mode,), value)

    def recognizes(self, private: bool, mode: int) -> bool:
        """Whether this model implements a mode."""
        return (private, mode) in self._modes

    def clear_mode(self, mode: int, private: bool = False) -> None:
        """Clear a single terminal mode."""
        self._apply_many(private, (mode,), False)

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
