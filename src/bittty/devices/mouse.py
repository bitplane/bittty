"""Mouse input encoder: xterm mouse reports and the DEC locator protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import constants
from ..options import DEC_LOCATOR, XTERM_EXTRAS
from ..present import PointerModeChanged
from .modes import ModeEffect, MouseEncoding, MouseProtocol

if TYPE_CHECKING:
    from .board import Board
    from ..operations import Operation
from .base import Device

# DEC locator button bits for the Pb field (VT330/VT340).
_LOCATOR_BUTTON_BIT = {0: 4, 1: 2, 2: 1}


class MouseDevice(Device):
    """Owns mouse presentation state and emits mouse input reports."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.x = 0
        self.y = 0
        self.pixel: tuple[int, int] | None = None  # the pointer's 0-based pixel, when the chrome knows it
        self.show = False
        self.locator_pixels = False
        self.reset()
        self._button_mask = 0
        self._pressed: set[int] = set()  # buttons currently held (drives 1002 drag motion)
        self.handlers = {}
        if XTERM_EXTRAS in board.model.provides:
            self.handlers["XTSMPOINTER"] = self.set_pointer_mode
        if DEC_LOCATOR in board.model.provides:
            # A terminal without a locator port does not recognise these at all,
            # which is a different thing from having one with nothing attached:
            # that answers DECRQLP with "locator unavailable" (CSI 0 & w).
            self.handlers.update(
                {
                    "DECELR": self.enable_locator,
                    "DECSLE": self.select_locator_events,
                    "DECRQLP": self.request_locator_position,
                    "DECEFR": self.set_filter_rectangle,
                }
            )

    def reset(self) -> None:
        """Power-on (RIS): no tracking protocol, legacy encoding, the locator off."""
        self.protocol = MouseProtocol.OFF
        self.encoding = MouseEncoding.LEGACY  # modes 1005/1006/1015/1016 select the others

    @property
    def protocol(self) -> MouseProtocol:
        """The application mouse protocol: modes 9/1000/1002/1003 select it, DECELR selects the locator."""
        return self._protocol

    @protocol.setter
    def protocol(self, protocol: MouseProtocol) -> None:
        # The locator's registers live only while it owns tracking.
        if protocol is not MouseProtocol.LOCATOR:
            self.locator_enabled = 0  # 0 off, 1 on, 2 one-shot
            self.locator_filter: tuple[int, int, int, int] | None = None  # top, left, bottom, right
            self.locator_report_down = False
            self.locator_report_up = False
        self._protocol = protocol

    def capture(self) -> str:
        """The physical events the chrome must capture for the selected protocol."""
        protocol = self.protocol
        if protocol in (MouseProtocol.ANY, MouseProtocol.LOCATOR):
            return "any"
        if protocol is MouseProtocol.BUTTON:
            return "button"
        if protocol in (MouseProtocol.X10, MouseProtocol.NORMAL):
            return "basic"
        if self.board.modes.alternate_scroll_mode and self.board.blitter.in_alt_screen:
            return "basic"
        return "off"

    def _select(self, protocol: MouseProtocol) -> None:
        self.protocol = protocol
        self.board.modes.reconcile(ModeEffect.MOUSE_CAPTURE)

    # --- DEC locator control functions --- #

    def set_pointer_mode(self, operation: Operation) -> None:
        """XTSMPOINTER — when the chrome hides the pointer while typing; no parameter is xterm's 1."""
        params = operation.args[0]
        mode = params[0] if params and params[0] is not None else 1
        if 0 <= mode <= 3:
            self.board.present(PointerModeChanged(mode))

    def enable_locator(self, operation: Operation) -> None:
        """DECELR — enable/disable locator reporting; ps2==1 selects pixel coordinates."""
        ps1, ps2 = operation.args
        self.locator_pixels = ps2 == 1
        if ps1 in (1, 2):
            self._select(MouseProtocol.LOCATOR)
            self.locator_enabled = ps1
            self.locator_filter = None  # DECELR always cancels the filter rectangle
        else:
            self._disable_locator()

    def _disable_locator(self) -> None:
        """Turn the locator off, and tracking with it only when the locator owns it."""
        self._select(MouseProtocol.OFF if self.protocol is MouseProtocol.LOCATOR else self.protocol)

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
        """DECEFR — report once the locator leaves this rectangle; an omitted edge is the locator's position."""
        if not self.locator_enabled:
            return
        row, col = self._locator_position()
        edges = [*operation.args[0][:4], None, None, None]
        self.locator_filter = tuple(
            edge if edge is not None else here for edge, here in zip(edges, (row, col, row, col))
        )
        self._check_filter()

    def _locator_position(self) -> tuple[int, int]:
        """The 1-based (row, column) DECLRP reports: in cells, or in pixels when DECELR asked for them."""
        if not self.locator_pixels:
            return self.y, self.x
        cell_width, cell_height = self.board.caps.cell_px or (1, 1)
        px, py = self.pixel or ((self.x - 1) * cell_width, (self.y - 1) * cell_height)
        return py + 1, px + 1

    def _check_filter(self) -> None:
        """Report (once) that the locator is outside the filter rectangle."""
        top, left, bottom, right = self.locator_filter
        row, col = self._locator_position()
        if not (top <= row <= bottom and left <= col <= right):
            self._emit_locator(10)  # locator left the filter rectangle
            self.locator_filter = None
            self._maybe_one_shot()

    def request_locator_position(self, operation: Operation) -> None:
        """DECRQLP — report the locator position now (or that it is unavailable)."""
        if not self.locator_enabled:
            self.board.host.write(f"{constants.ESC}[0&w", flush=True)
            return
        self._emit_locator(1)  # event 1 == response to an explicit request
        self._maybe_one_shot()

    def _emit_locator(self, event: int) -> None:
        row, col = self._locator_position()
        self.board.host.write(f"{constants.ESC}[{event};{self._button_mask};{row};{col};1&w", flush=True)

    def _maybe_one_shot(self) -> None:
        if self.locator_enabled == 2:
            self._disable_locator()

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
            self._check_filter()

    # --- input --- #

    def input_mouse(
        self,
        x: int,
        y: int,
        button: int,
        event_type: str,
        modifiers: set[str],
        pixel: tuple[int, int] | None = None,
    ) -> None:
        """
        Handle mouse input, cache position, and send appropriate sequence to the host.

        Args:
            x: 1-based mouse column.
            y: 1-based mouse row.
            button: The button that was pressed/released.
            event_type: "press", "release", or "move".
            modifiers: A set of active modifiers ("shift", "meta", "ctrl").
            pixel: the pointer's 0-based pixel position in the text area, if the chrome knows it
                (SGR-Pixels mode reports it; without it, the cell's top-left pixel is reported).
        """
        self.x = x
        self.y = y
        self.pixel = pixel

        if self.locator_enabled:
            self._report_locator_event(button, event_type)

        protocol = self.protocol
        is_move = event_type == "move"
        if event_type == "press":
            if button < 3:  # wheel "presses" (64/65) have no release and are not drags
                self._pressed.add(button)
        elif event_type == "release":
            self._pressed.discard(button)

        # With no application mouse protocol active, xterm's alternate-scroll
        # mode turns wheel presses into cursor keys while the alternate screen
        # is displayed. Application mouse tracking always takes precedence.
        if (
            protocol is MouseProtocol.OFF
            and self.board.modes.alternate_scroll_mode
            and self.board.blitter.in_alt_screen
            and event_type == "press"
            and button in (constants.MOUSE_BUTTON_WHEEL_UP, constants.MOUSE_BUTTON_WHEEL_DOWN)
        ):
            self.board.keyboard.input_key("up" if button == constants.MOUSE_BUTTON_WHEEL_UP else "down")
            return

        if protocol is MouseProtocol.LOCATOR:
            return
        if protocol is MouseProtocol.OFF:
            return
        if protocol is MouseProtocol.X10 and event_type != "press":
            return
        if is_move and not (protocol is MouseProtocol.ANY or (protocol is MouseProtocol.BUTTON and self._pressed)):
            return

        mods = 0
        if protocol is not MouseProtocol.X10:
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

        if self.encoding in (MouseEncoding.SGR, MouseEncoding.SGR_PIXELS):
            final_char = "m" if event_type == "release" else "M"
            if self.encoding is MouseEncoding.SGR_PIXELS:
                cell_width, cell_height = self.board.caps.cell_px or (1, 1)
                px, py = pixel or ((x - 1) * cell_width, (y - 1) * cell_height)
                x, y = px + 1, py + 1
            self.board.host.write(f"{constants.ESC}[<{bits};{x};{y}{final_char}")
            return

        # Legacy X10 byte encoding: CSI M Cb Cx Cy, each value + 32. A release
        # cannot name its button here, so its low bits are 3.
        if event_type == "release":
            bits = (bits & ~3) | 3

        # The encoding selector is mutually exclusive; legacy is the default.
        if self.encoding is MouseEncoding.URXVT:
            self.board.host.write(f"{constants.ESC}[{32 + bits};{x};{y}M")
            return

        if self.encoding is MouseEncoding.UTF8:
            # Mode 1005 UTF-8-encodes the three X10 values and extends the
            # coordinate ceiling from 223 to 2015.
            self.board.host.write(
                f"{constants.ESC}[M{chr(32 + bits)}{chr(32 + min(max(x, 0), 2015))}{chr(32 + min(max(y, 0), 2015))}"
            )
            return

        report = b"\x1b[M" + bytes(
            (
                min(32 + bits, 255),
                32 + min(max(x, 0), 223),
                32 + min(max(y, 0), 223),
            )
        )
        self.board.host.write_bytes(report)
