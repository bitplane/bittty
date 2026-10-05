"""The console: the registers of the box the terminal lives in.

Window state (XTWINOPS), the linux console's setterm registers, the bells, the
answerback message, and the desktop settings a child sets by OSC (clipboard,
working directory, pointer shape, font). A terminal (chrome) actuates them from
the present events; the board only keeps them.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from .. import constants
from ..present import (
    Bell,
    ClipboardChanged,
    ConsoleRequest,
    CwdChanged,
    FontChanged,
    Notification,
    PointerShapeChanged,
    PromptMark,
    WindowRequest,
    WindowStateChanged,
)
from .base import Device

if TYPE_CHECKING:
    from ..operations import Operation
    from .board import Board


class ConsoleDevice(Device):
    """Keeps the window, bell, answerback and desktop registers, and answers for them."""

    def __init__(self, board: Board, margin_bell_columns: int = 10) -> None:
        if margin_bell_columns < 0:
            raise ValueError("margin_bell_columns must be non-negative")
        self.board = board
        # OSC desktop settings; terminals sync these.
        self.clipboard: dict[str, str] = {}  # OSC 52 selections
        self.cwd: str = ""  # OSC 7 reported working directory
        self.pointer_shape: str = ""  # OSC 22 mouse-pointer shape
        self.font: str = ""  # OSC 50 font selection
        # XTWINOPS window state; a windowing terminal actuates these.
        self.window_iconified: bool = False
        self.window_maximized: bool = False
        self.window_fullscreen: bool = False
        self.window_position: tuple[int, int] = (0, 0)
        # linux console setterm hardware registers; a display/audio backend actuates these.
        self.screen_blanked: bool = False
        self.blank_timeout: int = board.model.blank_timeout  # minutes; 0 = never
        self.bell_hz: int = 750
        self.bell_ms: int = 125
        self.vesa_powerdown: int = 0
        self.cursor_blink_ms: int = 0
        self.default_underline_color: int | None = None
        self.default_dim_color: int | None = None
        self.warning_bell_volume: int = 8  # DECSWBV (0-8)
        self.margin_bell_volume: int = 0  # DECSMBV (0-8)
        self.margin_bell_columns = margin_bell_columns
        self._margin_bell_latch: tuple[int, int] | None = None
        self._answerback: str = ""
        self._answerback_concealed = False
        self.handlers = {
            "C0_BEL": lambda op: self.bell(),
            "C0_ENQ": lambda op: self.send_answerback(),
            "DECSWBV": lambda op: setattr(self, "warning_bell_volume", op.args[0]),
            "DECSMBV": lambda op: setattr(self, "margin_bell_volume", op.args[0]),
            "XTWINOPS": self.handle_window_op,
            "LINUX_SETTERM": self.handle_setterm,
            "OSC_CLIPBOARD": self.handle_clipboard,
            "OSC_CWD": self.handle_cwd,
            "OSC_NOTIFY": self.handle_notify,
            "OSC_SHELL_MARK": self.handle_shell_mark,
            "OSC_POINTER_SHAPE": self.handle_pointer_shape,
            "OSC_FONT": self.handle_font,
        }

    # --- bells --- #

    def bell(self) -> None:
        """Ring the terminal bell: pushed to the terminal (chrome) as a present event."""
        modes = self.board.modes
        self.board.present(Bell())
        if modes.bell_urgent:
            self.request_window("urgent")
        if modes.bell_raise:
            self.request_window("raise")

    def request_window(self, kind: str) -> None:
        """Present one window-manager action request; delivered, never stored."""
        self.board.present(WindowRequest(kind))

    def reset_margin_bell(self) -> None:
        """Re-arm the xterm margin bell after its mode changes."""
        self._margin_bell_latch = None

    def check_margin_bell(self) -> None:
        """Ring once when a printable keystroke occurs in the right-margin zone."""
        if not self.board.modes.margin_bell or self.margin_bell_columns == 0:
            self._margin_bell_latch = None
            return
        cursor = self.board.cursor
        blitter = self.board.blitter
        inside_margins = (
            blitter.scroll_top <= cursor.y <= blitter.scroll_bottom
            and blitter.left_margin <= cursor.display_x <= blitter.right_margin
        )
        right = blitter.right_margin if inside_margins else self.board.width - 1
        in_zone = cursor.display_x >= max(0, right + 1 - self.margin_bell_columns)
        latch = (cursor.y, right)
        if not in_zone:
            self._margin_bell_latch = None
        elif self._margin_bell_latch != latch:
            self._margin_bell_latch = latch
            self.bell()

    # --- answerback --- #

    @property
    def answerback(self) -> str | None:
        """Configured answerback, or None while DECCANSM conceals it."""
        return None if self._answerback_concealed else self._answerback

    @answerback.setter
    def answerback(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("answerback must be a string")
        self._answerback = value
        self._answerback_concealed = False

    @property
    def answerback_concealed(self) -> bool:
        return self._answerback_concealed

    def set_answerback_concealed(self, concealed: bool) -> None:
        """Conceal irreversibly until a new message is assigned."""
        if concealed:
            self._answerback_concealed = True

    def send_answerback(self) -> None:
        """ENQ — transmit the stored secret without exposing it through the public getter."""
        if self._answerback:
            self.board.host.write(self._answerback, flush=True)

    # --- OSC desktop settings --- #

    def handle_cwd(self, operation: Operation) -> None:
        """OSC 7 — record the reported working directory."""
        self.cwd = operation.args[0]
        self.board.present(CwdChanged(self.cwd))

    def handle_notify(self, operation: Operation) -> None:
        """OSC 9 / 777 / 99 — a desktop notification; delivered, never stored."""
        self.board.present(Notification(operation.args[0]))

    def handle_shell_mark(self, operation: Operation) -> None:
        """OSC 133 — a shell-integration prompt/command mark; delivered, never stored."""
        self.board.present(PromptMark(operation.args[0], self.board.cursor.y))

    def handle_pointer_shape(self, operation: Operation) -> None:
        """OSC 22 — the requested mouse-pointer shape."""
        self.pointer_shape = operation.args[0]
        self.board.present(PointerShapeChanged(self.pointer_shape))

    def handle_font(self, operation: Operation) -> None:
        """OSC 50 — set the font, or answer a query (data == '?') with the current one."""
        data = operation.args[0]
        if data == "?":
            self.board.host.write(f"\x1b]50;{self.font}\x07", flush=True)
        else:
            self.font = data
            self.board.present(FontChanged(data))

    def handle_clipboard(self, operation: Operation) -> None:
        """OSC 52 — set the clipboard, or answer a query with its current contents."""
        selection, payload = operation.args
        sel = selection or "c"
        if payload == "?":
            encoded = base64.b64encode(self.clipboard.get(sel, "").encode()).decode("ascii")
            self.board.host.write(f"\x1b]52;{sel};{encoded}\x07", flush=True)
            return
        try:
            self.clipboard[sel] = base64.b64decode(payload).decode("utf-8", errors="replace")
        except ValueError:
            return  # ignore malformed base64
        self.board.present(ClipboardChanged(sel, self.clipboard[sel]))

    # --- XTWINOPS --- #

    def handle_window_op(self, operation: Operation) -> None:
        """XTWINOPS — window manipulation requests and reports; a terminal (chrome) actuates them."""
        params = operation.args[0]

        def at(i: int) -> int:
            return params[i] if len(params) > i and params[i] is not None else 0

        op = at(0)
        board = self.board
        if op == 1:  # de-iconify
            self.window_iconified = False
            self._present_window_state()
        elif op == 2:  # iconify
            self.window_iconified = True
            self._present_window_state()
        elif op == 3:  # move window to (x, y)
            self.window_position = (at(1), at(2))
            self._present_window_state()
        elif op in (5, 6, 7):  # raise / lower / refresh
            self.request_window({5: "raise", 6: "lower", 7: "refresh"}[op])
        elif op == 8 and len(params) >= 3:  # resize text area to rows;cols
            self._resize_from_host(params[2] or board.width, params[1] or board.height)
        elif op == 9:  # maximize (0 restore, 1 maximize)
            self.window_maximized = at(1) == 1
            self._present_window_state()
        elif op == 10:  # fullscreen (0 off, 1 on, 2 toggle)
            self.window_fullscreen = (not self.window_fullscreen) if at(1) == 2 else at(1) == 1
            self._present_window_state()
        elif op == 11:  # report iconify state
            board.host.write(f"\x1b[{2 if self.window_iconified else 1}t", flush=True)
        elif op == 13:  # report window position
            x, y = self.window_position
            board.host.write(f"\x1b[3;{x};{y}t", flush=True)
        elif op in (14, 15):  # report window / screen size in pixels (from TerminalCaps)
            w, h = board.caps.window_px or (0, 0)
            board.host.write(f"\x1b[{4 if op == 14 else 5};{h};{w}t", flush=True)
        elif op == 16:  # report cell size in pixels (from TerminalCaps)
            w, h = board.caps.cell_px or (0, 0)
            board.host.write(f"\x1b[6;{h};{w}t", flush=True)
        elif op in (18, 19):  # report text-area / screen size in characters
            board.host.write(f"\x1b[{8 if op == 18 else 9};{board.height};{board.width}t", flush=True)
        elif op == 20:  # report icon label
            board.host.write(f"\x1b]L{board.title.reported(board.title.icon_title)}\x1b\\", flush=True)
        elif op == 21:  # report window title
            board.host.write(f"\x1b]l{board.title.reported(board.title.title)}\x1b\\", flush=True)
        elif op == 22:  # save title to the stack
            board.title.push()
        elif op == 23:  # restore title from the stack
            board.title.pop()
        elif op >= 24:  # DECSLPP — resize to Ps (>= 24) lines
            self._resize_from_host(board.width, op)

    def _resize_from_host(self, width: int, height: int) -> None:
        """Apply a resize the *child* asked for, within the host-request ceiling.

        XTWINOPS 8 and DECSLPP take their dimensions straight off the wire, so
        `CSI 8;99999;99999 t` would otherwise allocate a ten-billion-cell grid
        and take the embedding application down with it. A resize reported by
        the chrome is a physical fact and goes through Board.resize unbounded.
        """
        self.board.resize(
            max(1, min(width, constants.MAX_HOST_COLUMNS)),
            max(1, min(height, constants.MAX_HOST_ROWS)),
        )

    def _present_window_state(self) -> None:
        self.board.present(
            WindowStateChanged(
                self.window_iconified, self.window_maximized, self.window_fullscreen, self.window_position
            )
        )

    # --- linux setterm --- #

    def handle_setterm(self, operation: Operation) -> None:
        """linux `setterm` CSI...] — update the console's hardware registers."""
        params = operation.args[0]
        op = params[0] if params and params[0] is not None else 0
        arg = params[1] if len(params) > 1 and params[1] is not None else 0
        board = self.board
        if op == 1:
            self.default_underline_color = arg
        elif op == 2:
            self.default_dim_color = arg
        elif op == 8:
            board.style.set_default()  # make current attributes the default
        elif op == 9:
            self.blank_timeout = arg
        elif op == 10:
            self.bell_hz = arg
        elif op == 11:
            self.bell_ms = arg
        elif op == 12:
            board.present(ConsoleRequest("switch", arg))
        elif op == 13:
            self.screen_blanked = False
        elif op == 14:
            self.vesa_powerdown = arg
        elif op == 15:
            board.present(ConsoleRequest("previous", 0))
        elif op == 16:
            self.cursor_blink_ms = arg
