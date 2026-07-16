"""Mouse input encoder: xterm mouse reports and the DEC locator protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import constants

if TYPE_CHECKING:
    from .board import TerminalBoard
    from ..operations import Operation
from .base import Device

# DEC locator button bits for the Pb field (VT330/VT340).
_LOCATOR_BUTTON_BIT = {0: 4, 1: 2, 2: 1}


class MouseDevice(Device):
    """Owns mouse presentation state and emits mouse input reports."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.x = 0
        self.y = 0
        self.show = False
        # DEC locator state
        self.locator_enabled = 0  # 0 off, 1 on, 2 one-shot
        self.locator_pixels = False
        self.locator_report_down = False
        self.locator_report_up = False
        self.locator_filter: tuple[int, int, int, int] | None = None  # top, left, bottom, right
        self._button_mask = 0
        self._pressed: set[int] = set()  # buttons currently held (drives 1002 drag motion)
        self.handlers = {
            "DECELR": self.enable_locator,
            "DECSLE": self.select_locator_events,
            "DECRQLP": self.request_locator_position,
            "DECEFR": self.set_filter_rectangle,
        }

    # --- DEC locator control functions --- #

    def enable_locator(self, operation: Operation) -> None:
        """DECELR — enable/disable locator reporting; ps2==1 selects pixel coordinates."""
        ps1, ps2 = operation.args
        self.locator_enabled = ps1 if ps1 in (0, 1, 2) else 0
        self.locator_pixels = ps2 == 1
        if self.locator_enabled == 0:
            self.locator_filter = None

    def select_locator_events(self, operation: Operation) -> None:
        """DECSLE — choose whether button presses/releases trigger reports."""
        for param in operation.args[0]:
            if param == 0:
                self.locator_report_down = self.locator_report_up = False
            elif param == 1:
                self.locator_report_down = True
            elif param == 2:
                self.locator_report_down = False
            elif param == 3:
                self.locator_report_up = True
            elif param == 4:
                self.locator_report_up = False

    def set_filter_rectangle(self, operation: Operation) -> None:
        """DECEFR — report once the locator leaves this rectangle."""
        params = operation.args[0]
        self.locator_filter = tuple(params[:4]) if len(params) >= 4 else None

    def request_locator_position(self, operation: Operation) -> None:
        """DECRQLP — report the locator position now (or that it is unavailable)."""
        if not self.locator_enabled:
            self.board.host.write(f"{constants.ESC}[0&w", flush=True)
            return
        self._emit_locator(1)  # event 1 == response to an explicit request
        self._maybe_one_shot()

    def _emit_locator(self, event: int) -> None:
        self.board.host.write(f"{constants.ESC}[{event};{self._button_mask};{self.y};{self.x};1&w", flush=True)

    def _maybe_one_shot(self) -> None:
        if self.locator_enabled == 2:
            self.locator_enabled = 0

    def _report_locator_event(self, button: int, event_type: str) -> None:
        if event_type == "press":
            self._button_mask |= _LOCATOR_BUTTON_BIT.get(button, 0)
            if self.locator_report_down:
                self._emit_locator(2 + button * 2)  # 2/4/6 = left/middle/right down
                self._maybe_one_shot()
        elif event_type == "release":
            self._button_mask &= ~_LOCATOR_BUTTON_BIT.get(button, 0)
            if self.locator_report_up:
                self._emit_locator(3 + button * 2)  # 3/5/7 = left/middle/right up
                self._maybe_one_shot()
        elif event_type == "move" and self.locator_filter is not None:
            top, left, bottom, right = self.locator_filter
            if not (top <= self.y <= bottom and left <= self.x <= right):
                self._emit_locator(10)  # locator left the filter rectangle
                self.locator_filter = None
                self._maybe_one_shot()

    # --- input --- #

    def input_mouse(self, x: int, y: int, button: int, event_type: str, modifiers: set[str]) -> None:
        """
        Handle mouse input, cache position, and send appropriate sequence to the host.

        Args:
            x: 1-based mouse column.
            y: 1-based mouse row.
            button: The button that was pressed/released.
            event_type: "press", "release", or "move".
            modifiers: A set of active modifiers ("shift", "meta", "ctrl").
        """
        self.x = x
        self.y = y

        if self.locator_enabled:
            self._report_locator_event(button, event_type)

        modes = self.board.modes
        is_move = event_type == "move"
        if event_type == "press":
            if button < 3:  # wheel "presses" (64/65) have no release and are not drags
                self._pressed.add(button)
        elif event_type == "release":
            self._pressed.discard(button)

        # Motion reports need any-motion tracking (1003), or button tracking (1002)
        # with a button held (a drag). Press/release need any tracking mode at all.
        if is_move and not (modes.mouse_any_tracking or (modes.mouse_button_tracking and self._pressed)):
            return
        if not is_move and not modes.mouse_tracking:
            return

        mods = 0
        if "shift" in modifiers:
            mods |= constants.MOUSE_MOD_SHIFT
        if "meta" in modifiers:
            mods |= constants.MOUSE_MOD_META
        if "ctrl" in modifiers:
            mods |= constants.MOUSE_MOD_CTRL

        if is_move:  # motion flag + the dragged button (3 = none)
            bits = 32 | (min(self._pressed) if self._pressed else 3) | mods
        else:
            bits = button | mods

        if modes.mouse_sgr_mode:
            final_char = "m" if event_type == "release" else "M"
            self.board.host.write(f"{constants.ESC}[<{bits};{x};{y}{final_char}")
            return

        # Legacy X10 byte encoding: CSI M Cb Cx Cy, each value + 32. A release
        # cannot name its button here, so its low bits are 3.
        if event_type == "release":
            bits = (bits & ~3) | 3
        self.board.host.write(f"{constants.ESC}[M{chr(32 + bits)}{chr(32 + min(x, 223))}{chr(32 + min(y, 223))}")
