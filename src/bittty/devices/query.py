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
            "DA3": self.report_tertiary_device_attributes,
            "DECRQM": self.report_mode_status,
            "DECRQSS": self.report_status_string,
            "OSC_CLIPBOARD": self.handle_clipboard,
            "XTWINOPS": self.handle_window_op,
            "DECSCL": self.set_conformance_level,
            "OSC_CWD": lambda op: setattr(self.board, "cwd", op.args[0]),
            "OSC_NOTIFY": lambda op: self.board.notifications.append(op.args[0]),
            "OSC_SHELL_MARK": lambda op: self.board.prompt_marks.append((op.args[0], self.board.cursor.y)),
            "LINUX_SETTERM": self.handle_setterm,
            "DECSWBV": lambda op: setattr(self.board, "warning_bell_volume", op.args[0]),
            "DECSMBV": lambda op: setattr(self.board, "margin_bell_volume", op.args[0]),
            "DECRQCRA": self.request_checksum,
            "XTGETTCAP": self.request_termcap,
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

    def report_tertiary_device_attributes(self, operation: Operation) -> None:
        response = self.board.personality.da3_response
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

    def handle_window_op(self, operation: Operation) -> None:
        """XTWINOPS — report the terminal size, resize it, or push/pop the title stack."""
        params = operation.args[0]
        op = params[0] if params and params[0] is not None else 0
        if op in (18, 19):  # report text-area / screen size in characters
            code = 8 if op == 18 else 9
            self.board.host.write(f"\x1b[{code};{self.board.height};{self.board.width}t", flush=True)
        elif op == 8 and len(params) >= 3:  # resize text area to rows;cols
            rows = params[1] or self.board.height
            cols = params[2] or self.board.width
            self.board.resize(cols, rows)
        elif op == 22:  # save title to the stack
            self.board.title.push()
        elif op == 23:  # restore title from the stack
            self.board.title.pop()

    def set_conformance_level(self, operation: Operation) -> None:
        """DECSCL — record the requested conformance level (behaviourally a no-op)."""
        params = operation.args[0]
        if params and params[0] is not None:
            self.board.conformance_level = params[0]

    def handle_setterm(self, operation: Operation) -> None:
        """linux `setterm` CSI...] — update the board's hardware registers."""
        params = operation.args[0]
        op = params[0] if params and params[0] is not None else 0
        arg = params[1] if len(params) > 1 and params[1] is not None else 0
        board = self.board
        if op == 1:
            board.default_underline_color = arg
        elif op == 2:
            board.default_dim_color = arg
        elif op == 8:
            board.style.set_default()  # make current attributes the default
        elif op == 9:
            board.blank_timeout = arg
        elif op == 10:
            board.bell_hz = arg
        elif op == 11:
            board.bell_ms = arg
        elif op == 12:
            board.console_requests.append(("switch", arg))
        elif op == 13:
            board.screen_blanked = False
        elif op == 14:
            board.vesa_powerdown = arg
        elif op == 15:
            board.console_requests.append(("previous", 0))
        elif op == 16:
            board.cursor_blink_ms = arg

    def request_checksum(self, operation: Operation) -> None:
        """DECRQCRA — reply DCS Pid ! ~ HHHH ST with a 16-bit checksum of a rectangle.

        This is the DEC character-value form: the negated sum of the codepoints in
        the area, masked to 16 bits. (xterm can fold SGR attributes in too; that is a
        personality detail we can add when a terminal needs it.)
        """
        params = operation.args[0]

        def at(index: int, default: int) -> int:
            value = params[index] if len(params) > index and params[index] is not None else None
            return default if value is None else value

        pid = params[0] if params and params[0] is not None else 0
        width, height = self.board.width, self.board.height
        top = max(0, min(at(2, 1) - 1, height - 1))
        left = max(0, min(at(3, 1) - 1, width - 1))
        bottom = max(top, min(at(4, height) - 1, height - 1))
        right = max(left, min(at(5, width) - 1, width - 1))
        buffer = self.board.screen.current_buffer
        total = 0
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                char = buffer.get_cell(x, y)[1]
                total += ord(char) if char else 0x20
        self.board.host.write(f"\x1bP{pid}!~{(-total) & 0xFFFF:04X}\x1b\\", flush=True)

    def request_termcap(self, operation: Operation) -> None:
        """XTGETTCAP — answer hex-encoded termcap/terminfo capability requests."""
        caps = self._termcaps()
        for token in operation.args[0].split(";"):
            try:
                name = bytes.fromhex(token).decode("ascii")
            except ValueError:
                continue
            value = caps.get(name)
            if value is None:  # unknown capability -> negative reply
                self.board.host.write(f"\x1bP0+r{token}\x1b\\", flush=True)
            else:
                name_hex = name.encode("ascii").hex().upper()
                value_hex = value.encode("ascii").hex().upper()
                self.board.host.write(f"\x1bP1+r{name_hex}={value_hex}\x1b\\", flush=True)

    def _termcaps(self) -> dict[str, str]:
        """The capability strings this personality answers XTGETTCAP with."""
        personality = self.board.personality
        colors = {"monochrome": "2", "16": "16", "256": "256", "truecolor": "256"}.get(personality.color_depth, "256")
        caps = {"TN": personality.name, "Co": colors, "colors": colors}
        if personality.color_depth == "truecolor":
            caps["RGB"] = "8/8/8"
        return caps

    def handle_operation(self, operation: Operation) -> None:
        handler = self.handlers.get(operation.name)
        if handler is not None:
            handler(operation)
