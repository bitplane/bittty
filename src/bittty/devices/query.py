"""Query operation handler for the current Terminal state."""

from __future__ import annotations

import base64

from typing import TYPE_CHECKING

from ..operations import Operation
from ..style import style_to_ansi

if TYPE_CHECKING:
    from .board import TerminalBoard


class QueryDevice:
    """Applies terminal query operations to the current Terminal implementation."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.modes = board.modes
        self.handlers = {
            "CPR": self.report_cursor_position,
            "DSR": self.report_device_status,
            "DA1": self.report_primary_device_attributes,
            "DA2": self.report_secondary_device_attributes,
            "DECRQM": self.report_mode_status,
            "DECRQSS": self.report_status_string,
            "OSC_CLIPBOARD": self.handle_clipboard,
        }

    def report_cursor_position(self, operation: Operation) -> None:
        row = self.board.cursor.y + 1
        col = self.board.cursor.x + 1
        self.board.host.write(f"\033[{row};{col}R", flush=True)

    def report_device_status(self, operation: Operation) -> None:
        self.board.host.write("\033[0n", flush=True)

    def report_primary_device_attributes(self, operation: Operation) -> None:
        self.board.host.write(self.board.personality.da1_response, flush=True)

    def report_secondary_device_attributes(self, operation: Operation) -> None:
        response = self.board.personality.da2_response
        if response is not None:
            self.board.host.write(response, flush=True)

    def report_mode_status(self, operation: Operation) -> None:
        mode, private = operation.args
        status = self.modes.get_private_mode_status(mode) if private else self.modes.get_ansi_mode_status(mode)
        prefix = "?" if private else ""
        self.board.host.write(f"\033[{prefix}{mode};{status}$y", flush=True)

    def report_status_string(self, operation: Operation) -> None:
        """DECRQSS — answer a request for the current value of a setting."""
        request = operation.args[0]
        setting = self._status_string(request)
        if setting is not None:
            self.board.host.write(f"\x1bP1$r{setting}\x1b\\", flush=True)  # 1 = valid request
        else:
            self.board.host.write(f"\x1bP0$r{request}\x1b\\", flush=True)  # 0 = unsupported

    def _status_string(self, request: str) -> str | None:
        if request == "m":  # SGR
            ansi = style_to_ansi(self.board.style.current)
            params = ansi[2:-1] if ansi else "0"
            return f"{params}m"
        if request == "r":  # DECSTBM - top/bottom margins
            return f"{self.board.screen.scroll_top + 1};{self.board.screen.scroll_bottom + 1}r"
        if request == " q":  # DECSCUSR - cursor style
            base = {"block": 1, "underline": 3, "bar": 5}.get(self.board.cursor.shape, 1)
            style = base if self.board.modes.cursor_blinking else base + 1
            return f"{style} q"
        return None

    def handle_clipboard(self, operation: Operation) -> None:
        """OSC 52 — set the clipboard, or answer a query with its current contents."""
        selection, payload = operation.args
        sel = selection or "c"
        if payload == "?":
            encoded = base64.b64encode(self.board.clipboard.get(sel, "").encode()).decode("ascii")
            self.board.host.write(f"\x1b]52;{sel};{encoded}\x07", flush=True)
            return
        try:
            self.board.clipboard[sel] = base64.b64decode(payload).decode("utf-8", errors="replace")
        except ValueError:
            pass  # ignore malformed base64

    def handle_operation(self, operation: Operation) -> None:
        handler = self.handlers.get(operation.name)
        if handler is not None:
            handler(operation)
