"""Declarative ANSI/DEC modes resolved through model capability profiles."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import Enum
from operator import attrgetter
from typing import TYPE_CHECKING

from .. import mode_profiles as mp
from ..keyboard_styles import KeyboardStyle
from ..operations import Operation
from ..present import (
    AmbiguousWidthChanged,
    ChromeResourcesChanged,
    CursorBlinkChanged,
    CursorVisibilityChanged,
    GraphemeClusteringChanged,
    KeyboardIndicatorChanged,
    KeyboardLockChanged,
    MouseCaptureChanged,
    PresentEvent,
    ReverseScreenChanged,
    SmoothScrollChanged,
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
    KEYBOARD_INDICATOR = "keyboard-indicator"
    CHROME_RESOURCES = "chrome-resources"
    SMOOTH_SCROLL = "smooth-scroll"


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
    SGR_PIXELS = "sgr-pixels"
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
    effects: frozenset[ModeEffect] = frozenset()
    save_fn: Callable[[ModeDevice], None] | None = None
    restore_fn: Callable[[ModeDevice], None] | None = None

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
            return 1 if getattr(device, self.attr) != self.invert else 2
        return 0


# --- side effects for modes that do more than flip a flag --- #


def _status_of(is_set: Callable[[ModeDevice], bool]) -> Callable[[ModeDevice], int]:
    """A DECRQM status function: 1 (set) while is_set holds, else 2 (reset)."""
    return lambda device: 1 if is_set(device) else 2


def _register(owner: Callable[[ModeDevice], object], attr: str) -> dict:
    """A mode kept as a flag on another device: its setter and its DECRQM status."""
    return {
        "apply_fn": lambda device, value: setattr(owner(device), attr, value),
        "status_fn": _status_of(lambda device: getattr(owner(device), attr)),
    }


_KEYBOARD_MODES = (1050, 1051, 1052, 1053, 1060, 1061)


def _save_keyboard_style(device: ModeDevice) -> None:
    keyboard = device.board.keyboard
    keyboard.saved_style = keyboard.style
    # Xterm uses one shared save slot for this entire selection family.
    for number in _KEYBOARD_MODES:
        if (True, number) in device._modes:
            device._saved_private_modes[number] = None


def _restore_keyboard_style(device: ModeDevice) -> None:
    device.board.keyboard.style = device.board.keyboard.saved_style


def _keyboard_style(capability: str, number: int, style: KeyboardStyle) -> ModeSpec:
    return ModeSpec(
        capability,
        number,
        True,
        queryable=True,
        apply_fn=lambda d, enabled: setattr(d.board.keyboard, "style", style if enabled else KeyboardStyle.DEFAULT),
        status_fn=_status_of(lambda d: d.board.keyboard.style is style),
        save_fn=_save_keyboard_style,
        restore_fn=_restore_keyboard_style,
    )


def _mouse_mode(
    capability: str,
    number: int,
    attr: str,
    member: MouseProtocol | MouseEncoding,
    off: MouseProtocol | MouseEncoding,
    effects: frozenset[ModeEffect],
) -> ModeSpec:
    """One of a mutually exclusive mouse selection: setting selects it, resetting deselects it only if selected."""

    def apply(device: ModeDevice, enabled: bool) -> None:
        mouse = device.board.mouse
        if enabled or getattr(mouse, attr) is member:
            setattr(mouse, attr, member if enabled else off)

    return ModeSpec(
        capability,
        number,
        True,
        queryable=True,
        apply_fn=apply,
        status_fn=_status_of(lambda device: getattr(device.board.mouse, attr) is member),
        effects=effects,
    )


def _mouse_protocol(capability: str, number: int, protocol: MouseProtocol) -> ModeSpec:
    return _mouse_mode(capability, number, "protocol", protocol, MouseProtocol.OFF, _MOUSE_EFFECT)


def _mouse_encoding(capability: str, number: int, encoding: MouseEncoding) -> ModeSpec:
    return _mouse_mode(capability, number, "encoding", encoding, MouseEncoding.LEGACY, frozenset())


def _set_delete_mode(device: ModeDevice, value: bool) -> None:
    device.board.keyboard.delete_mode = value


def _save_delete(device: ModeDevice) -> None:
    device.board.keyboard.saved_delete_mode = device.board.keyboard.delete_mode


def _restore_delete(device: ModeDevice) -> None:
    device.board.keyboard.delete_mode = device.board.keyboard.saved_delete_mode


def _decanm(device: ModeDevice, value: bool) -> None:
    device.board.set_vt52(not value)


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
        for page in device.board.blitter.videos:
            page.reset_line_attributes()
    else:
        # Disabling left/right margin mode resets the margins to the full width.
        device.board.blitter.reset_left_right_margins()


_column_status = _status_of(lambda device: device.board.width == 132)
_alt_screen_status = _status_of(lambda device: device.board.blitter.in_alt_screen)


def _page_coupling(device: ModeDevice, value: bool) -> None:
    if value:
        device.board.blitter.couple_display()


def _host_line_mode(field: str) -> dict:
    """A communication mode kept in the host line's settings: its setter and its DECRQM status."""

    def apply(device: ModeDevice, value: bool) -> None:
        device.board.comm.update(**{field: value})

    return {"apply_fn": apply, "status_fn": _status_of(lambda device: getattr(device.board.comm.line, field))}


def _right_to_left(device: ModeDevice, value: bool) -> None:
    device.board.blitter.set_right_to_left(value)


def _crt_saver(device: ModeDevice, value: bool) -> None:
    """DECCRTSM drives the blank-timeout register: the VT510 blanks after 30 minutes."""
    device.board.console.blank_timeout = 30 if value else 0


_crt_saver_status = _status_of(lambda device: bool(device.board.console.blank_timeout))


def _ambiguous_width(device: ModeDevice, value: bool) -> None:
    device.board.blitter.set_ambiguous_width(2 if value else 1)


def _ambiguous_width_double(device: ModeDevice) -> bool:
    return device.board.blitter.width_policy.ambiguous_width == 2


def _grapheme_clustering(device: ModeDevice, value: bool) -> None:
    device.board.blitter.set_grapheme_clustering(value)


def _printer(device: ModeDevice):
    return device.board.printer


def _ignore_null(device: ModeDevice, value: bool) -> None:
    device.board.printer.set_ignore_null(value)


_ignore_null_status = _status_of(lambda device: device.board.printer.configuration.ignore_null)


def _conceal_answerback(device: ModeDevice, value: bool) -> None:
    device.board.console.set_answerback_concealed(value)


_conceal_answerback_status = _status_of(lambda device: device.board.console.answerback_concealed)


def _inband_resize(device: ModeDevice, value: bool) -> None:
    if value:
        device.board.report_resize()


def _margin_bell(device: ModeDevice, value: bool) -> None:
    device.board.console.reset_margin_bell()


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
    ModeSpec(mp.DEC_ANSI, 2, True, "ansi_mode", default=True, queryable=True, apply_fn=_decanm),
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
    ModeSpec(
        mp.DEC_SMOOTH_SCROLL, 4, True, "smooth_scroll", queryable=True, effects=frozenset({ModeEffect.SMOOTH_SCROLL})
    ),
    ModeSpec(mp.DEC_ORIGIN, 6, True, "origin_mode", queryable=True),
    ModeSpec(mp.DEC_RIGHT_TO_LEFT, 34, True, "right_to_left", queryable=True, apply_fn=_right_to_left),
    # CRT settings the chrome carries out; it reads them here and from board.console.blank_timeout.
    ModeSpec(mp.DEC_INTERLACE, 9, True, "interlace", queryable=True),
    ModeSpec(mp.DEC_CRT_SAVER, 97, True, apply_fn=_crt_saver, status_fn=_crt_saver_status),
    ModeSpec(mp.DEC_OVERSCAN, 106, True, "overscan", queryable=True),
    ModeSpec(mp.DEC_AUTOWRAP, 7, True, "auto_wrap", default=True, queryable=True),
    ModeSpec(mp.DEC_AUTO_REPEAT, 8, True, "auto_repeat", default=True, queryable=True),
    ModeSpec(mp.MINTTY_APPLICATION_ESCAPE, 7727, True, "application_escape", queryable=True),
    ModeSpec(mp.MINTTY_ESCAPE_FS, 7728, True, "escape_sends_fs", queryable=True),
    _mouse_protocol(mp.XTERM_MOUSE_X10, 9, MouseProtocol.X10),
    ModeSpec(
        mp.XTERM_CURSOR_BLINK,
        12,
        True,
        "cursor_blinking",
        queryable=True,
        effects=frozenset({ModeEffect.CURSOR_BLINK}),
    ),
    ModeSpec(mp.DEC_PRINT_FORM_FEED, 18, True, **_register(_printer, "print_form_feed")),
    ModeSpec(mp.DEC_PRINT_EXTENT, 19, True, **_register(_printer, "print_extent")),
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
    # xterm's curses workaround (the more(1) fix): xterm 407 keeps and reports it, and nothing reads it.
    ModeSpec(mp.XTERM_MORE_FIX, 41, True, "more_fix", queryable=True),
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
    ModeSpec(
        mp.DEC_PAGE_COUPLING,
        64,
        True,
        "page_cursor_coupling",
        default=True,
        queryable=True,
        apply_fn=_page_coupling,
    ),
    ModeSpec(mp.DEC_TRANSMIT_RATE_LIMIT, 73, True, **_host_line_mode("rate_limited")),
    ModeSpec(mp.DEC_NO_CLEAR_COLUMN, 95, True, "no_clear_column_mode", queryable=True),
    ModeSpec(mp.DEC_AUTO_ANSWERBACK, 100, True, "auto_answerback", queryable=True),
    ModeSpec(mp.DEC_MODEM_CONTROL, 99, True, **_host_line_mode("modem_control")),
    ModeSpec(
        mp.DEC_CONCEAL_ANSWERBACK,
        101,
        True,
        apply_fn=_conceal_answerback,
        status_fn=_conceal_answerback_status,
    ),
    # The printer configuration holds this one; the printer's reset clears it on DECSTR too.
    ModeSpec(mp.DEC_IGNORE_NULL, 102, True, apply_fn=_ignore_null, status_fn=_ignore_null_status),
    ModeSpec(mp.DEC_HALF_DUPLEX, 103, True, **_host_line_mode("half_duplex")),
    # Keyboard indicators: 108/109 are keyboard state the host may drive; 110
    # selects whether the LEDs show that state or DECLL-loaded host indications.
    ModeSpec(
        mp.DEC_NUMLOCK,
        108,
        True,
        "num_lock_mode",
        queryable=True,
        effects=frozenset({ModeEffect.KEYBOARD_INDICATOR}),
    ),
    ModeSpec(
        mp.DEC_CAPSLOCK,
        109,
        True,
        "caps_lock_mode",
        queryable=True,
        effects=frozenset({ModeEffect.KEYBOARD_INDICATOR}),
    ),
    ModeSpec(
        mp.DEC_LED_HOST_INDICATOR,
        110,
        True,
        "led_host_indicator_mode",
        queryable=True,
        effects=frozenset({ModeEffect.KEYBOARD_INDICATOR}),
    ),
    _mouse_protocol(mp.XTERM_MOUSE_NORMAL, 1000, MouseProtocol.NORMAL),
    ModeSpec(mp.XTERM_FOCUS, 1004, True, "focus_reporting", queryable=True),
    _mouse_protocol(mp.XTERM_MOUSE_BUTTON, 1002, MouseProtocol.BUTTON),
    _mouse_protocol(mp.XTERM_MOUSE_ANY, 1003, MouseProtocol.ANY),
    _mouse_encoding(mp.XTERM_MOUSE_UTF8, 1005, MouseEncoding.UTF8),
    _mouse_encoding(mp.XTERM_MOUSE_SGR, 1006, MouseEncoding.SGR),
    _mouse_encoding(mp.XTERM_MOUSE_SGR_PIXELS, 1016, MouseEncoding.SGR_PIXELS),
    ModeSpec(
        mp.XTERM_ALTERNATE_SCROLL,
        1007,
        True,
        "alternate_scroll_mode",
        queryable=True,
        effects=_MOUSE_EFFECT,
    ),
    _mouse_encoding(mp.URXVT_MOUSE, 1015, MouseEncoding.URXVT),
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
    # A keyboard setting in xterm, not terminal state: RIS and DECSTR keep it.
    ModeSpec(
        mp.XTERM_DELETE,
        1037,
        True,
        queryable=True,
        apply_fn=_set_delete_mode,
        status_fn=_status_of(lambda d: d.board.keyboard.delete_sends_del),
        save_fn=_save_delete,
        restore_fn=_restore_delete,
    ),
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
        apply_fn=_ambiguous_width,
        status_fn=_status_of(_ambiguous_width_double),
        effects=frozenset({ModeEffect.WIDTH}),
    ),
)


MODE_SPECS += (
    ModeSpec(mp.CONTOUR_TEXT_REFLOW, 2028, True, "text_reflow", queryable=True),
    ModeSpec(mp.XTERM_READLINE_QUOTING, 2005, True, "readline_quoting", queryable=True),
    ModeSpec(mp.XTERM_READLINE_NEWLINE, 2006, True, "readline_newline", queryable=True),
    _keyboard_style(mp.XTERM_SUN_KEYS, 1051, KeyboardStyle.SUN),
    _keyboard_style(mp.XTERM_HP_KEYS, 1052, KeyboardStyle.HP),
    _keyboard_style(mp.XTERM_SCO_KEYS, 1053, KeyboardStyle.SCO),
    _keyboard_style(mp.XTERM_LEGACY_KEYS, 1060, KeyboardStyle.LEGACY),
    _keyboard_style(mp.XTERM_VT220_KEYS, 1061, KeyboardStyle.VT220),
    _keyboard_style(mp.XTERM_TERMCAP_KEYS, 1050, KeyboardStyle.TERMCAP),
)

# xterm resources the chrome carries out, by mode: (capability, name, xterm 407's default).
# The board keeps them and tells the chrome which are enabled.
CHROME_RESOURCES = {
    30: (mp.XTERM_SCROLLBAR, "scrollbar", False),
    35: (mp.XTERM_FONT_SHIFTING, "font-shifting", True),
    1010: (mp.XTERM_SCROLL_ON_OUTPUT, "scroll-on-output", True),
    1011: (mp.XTERM_SCROLL_ON_KEY, "scroll-on-key", False),
    1014: (mp.XTERM_FAST_SCROLL, "fast-scroll", True),
    1040: (mp.XTERM_KEEP_SELECTION, "keep-selection", True),
    1041: (mp.XTERM_SELECT_TO_CLIPBOARD, "select-to-clipboard", False),
    1044: (mp.XTERM_KEEP_CLIPBOARD, "keep-clipboard", False),
}


def _chrome_attr(name: str) -> str:
    return "chrome_" + name.replace("-", "_")


MODE_SPECS += tuple(
    ModeSpec(
        capability,
        number,
        True,
        _chrome_attr(name),
        default=default,
        queryable=True,
        effects=frozenset({ModeEffect.CHROME_RESOURCES}),
    )
    for number, (capability, name, default) in CHROME_RESOURCES.items()
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


# Modes whose setting is an action — entering VT52, clearing the screen, switching screens,
# saving the cursor — rather than a state that setting re-establishes.
_ACTION_MODES = frozenset({(True, 2), (True, 3), (True, 47), (True, 1047), (True, 1048), (True, 1049)})


class ModeDevice(Device):
    """Owns terminal mode state and applies mode operations via the mode table."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self._modes = resolve_mode_specs(board.model.capabilities, board.model.unsupported_modes)
        self._runtime_mode_status = {(private, number): status for private, number, status in board.model.fixed_modes}
        # None marks an action-mode whose save/restore hooks own the snapshot.
        self._saved_private_modes: dict[int, bool | None] = {}
        self._batch_depth = 0
        self._pending_effects: set[ModeEffect] = set()
        self._set_defaults()
        # Edge-trigger cache: the state each present event last carried (absent = never sent).
        # The chrome starts knowing two of them: its resources at their defaults, and
        # its keyboard LEDs all off, so a DECLL write that leaves them dark emits nothing.
        self._last: dict[ModeEffect, object] = {
            ModeEffect.CHROME_RESOURCES: self.chrome_resources(),
            ModeEffect.KEYBOARD_INDICATOR: (False, False, False),
        }
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
        initialized: set[str] = set()
        power_on = self.board.model.power_on_modes
        for spec in MODE_SPECS:
            if spec.attr is None or spec.attr in initialized:
                continue
            default = spec.default(self) if callable(spec.default) else spec.default
            default = default or (spec.private and spec.number in power_on)
            setattr(self, spec.attr, default)
            initialized.add(spec.attr)

        # DECKPAM/DECKPNM are escape controls, not SM/RM modes.
        self.application_keypad = False

    def reset(self, hard: bool = True, *, reconcile: bool = True) -> None:
        """Reset modes. hard restores every flag (RIS); soft is the DECSTR subset."""
        if hard:
            self._saved_private_modes.clear()
            self._set_defaults()
            fixed_grapheme = self._runtime_mode_status.get((True, 2027))
            self.grapheme_clustering = fixed_grapheme == 3
            self.board.blitter.set_grapheme_clustering(self.grapheme_clustering)
        else:
            # DECSTR soft reset — the widely-agreed subset (SGR is reset by the style device).
            self.insert_mode = False
            self.origin_mode = False
            self.cursor_visible = True
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
        state_of, event = _EFFECT_EVENTS[effect]
        state = state_of(self)
        if state is None or (not force and self._last.get(effect) == state):
            return
        self._last[effect] = state
        self.board.present(event(state))

    def chrome_resources(self) -> frozenset[str]:
        """The chrome resources this terminal has that are enabled."""
        return frozenset(
            name
            for number, (_, name, _) in CHROME_RESOURCES.items()
            if (True, number) in self._modes and getattr(self, _chrome_attr(name))
        )

    def set_cursor_blinking(self, enabled: bool) -> None:
        """Set cursor blink state and notify the attached terminal on an edge."""
        self.cursor_blinking = enabled
        self.reconcile(ModeEffect.CURSOR_BLINK)

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
            status = self.mode_status(True, param)
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
                    self._modes[(True, param)].restore_fn(self)
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

    def restorable_states(self) -> list[tuple[bool, int, bool]]:
        """(private, number, set) for each mode whose state setting or resetting it restores."""
        states = []
        for private, number in self._modes:
            status = self.mode_status(private, number)
            if status in (1, 2) and (private, number) not in _ACTION_MODES:
                states.append((private, number, status == 1))
        return states

    def mode_status(self, private: bool, mode: int) -> int:
        """DECRQM status: 0 not recognised, 1 set, 2 reset, 3 permanently set, 4 permanently reset."""
        key = (private, mode)
        if key in self._runtime_mode_status:
            return self._runtime_mode_status[key]
        entry = self._modes.get(key)
        return entry.status(self) if entry is not None else 0


def _ambiguous_width_state(device: ModeDevice) -> int | None:
    """1 or 2, on a terminal with mode 8840; None on one that cannot change it."""
    if not device.recognizes(True, 8840):
        return None
    return 2 if _ambiguous_width_double(device) else 1


def _indicator_state(device: ModeDevice) -> tuple[bool, bool, bool] | None:
    """The keyboard LEDs (num, caps, scroll); None on a terminal with no LEDs to speak of."""
    keyboard = device.board.keyboard
    if not keyboard.leds_fitted and not device.recognizes(True, 110):
        return None
    return keyboard.indicator_lights()


# Each frontend-facing effect: the state it reports (None: nothing to report) and its event.
_EFFECT_EVENTS: dict[ModeEffect, tuple[Callable[[ModeDevice], object], Callable[[object], PresentEvent]]] = {
    ModeEffect.MOUSE_CAPTURE: (lambda device: device.board.mouse.capture(), MouseCaptureChanged),
    ModeEffect.CURSOR: (attrgetter("cursor_visible"), CursorVisibilityChanged),
    ModeEffect.CURSOR_BLINK: (attrgetter("cursor_blinking"), CursorBlinkChanged),
    ModeEffect.REVERSE: (attrgetter("reverse_screen"), ReverseScreenChanged),
    ModeEffect.SYNC: (attrgetter("synchronized_output"), SyncOutputChanged),
    ModeEffect.WIDTH: (_ambiguous_width_state, AmbiguousWidthChanged),
    ModeEffect.GRAPHEME: (attrgetter("grapheme_clustering"), GraphemeClusteringChanged),
    ModeEffect.KEYBOARD_LOCK: (attrgetter("keyboard_locked"), KeyboardLockChanged),
    ModeEffect.KEYBOARD_INDICATOR: (_indicator_state, lambda lights: KeyboardIndicatorChanged(*lights)),
    ModeEffect.CHROME_RESOURCES: (ModeDevice.chrome_resources, ChromeResourcesChanged),
    ModeEffect.SMOOTH_SCROLL: (attrgetter("smooth_scroll"), SmoothScrollChanged),
}
