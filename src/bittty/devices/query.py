"""Query operation handler for the current board state."""

from __future__ import annotations

import base64

from typing import TYPE_CHECKING

from ..operations import Operation
from ..present import (
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
from ..style import style_to_ansi

if TYPE_CHECKING:
    from .board import Board


class QueryDevice(Device):
    """Applies terminal query operations to the current board implementation."""

    def __init__(self, board: Board) -> None:
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
            "OSC_CWD": self.handle_cwd,
            "OSC_NOTIFY": self.handle_notify,
            "OSC_SHELL_MARK": self.handle_shell_mark,
            "OSC_POINTER_SHAPE": self.handle_pointer_shape,
            "OSC_FONT": self.handle_font,
            "LINUX_SETTERM": self.handle_setterm,
            "DECSWBV": lambda op: setattr(self.board, "warning_bell_volume", op.args[0]),
            "DECSMBV": lambda op: setattr(self.board, "margin_bell_volume", op.args[0]),
            "DECRQCRA": self.request_checksum,
            "XTGETTCAP": self.request_termcap,
            "XTVERSION": self.report_version,
        }

    def handle_cwd(self, operation: Operation) -> None:
        """OSC 7 — record the reported working directory."""
        self.board.cwd = operation.args[0]
        self.board.present(CwdChanged(self.board.cwd))

    def handle_notify(self, operation: Operation) -> None:
        """OSC 9 / 777 / 99 — a desktop notification."""
        self.board.notifications.append(operation.args[0])
        self.board.present(Notification(operation.args[0]))

    def handle_shell_mark(self, operation: Operation) -> None:
        """OSC 133 — a shell-integration prompt/command mark."""
        self.board.prompt_marks.append((operation.args[0], self.board.cursor.y))
        self.board.present(PromptMark(operation.args[0], self.board.cursor.y))

    def handle_pointer_shape(self, operation: Operation) -> None:
        """OSC 22 — the requested mouse-pointer shape."""
        self.board.pointer_shape = operation.args[0]
        self.board.present(PointerShapeChanged(self.board.pointer_shape))

    def handle_font(self, operation: Operation) -> None:
        """OSC 50 — set the font, or answer a query (data == '?') with the current one."""
        data = operation.args[0]
        if data == "?":
            self.board.host.write(f"\x1b]50;{self.board.font}\x07", flush=True)
        else:
            self.board.font = data
            self.board.present(FontChanged(data))

    def report_version(self, operation: Operation) -> None:
        """XTVERSION (CSI > q) — reply DCS > | name version ST."""
        try:
            from importlib.metadata import version

            rev = version("bittty")
        except Exception:
            rev = "0"
        self.board.host.write(f"\x1bP>|bittty({rev})\x1b\\", flush=True)

    def report_cursor_position(self, operation: Operation) -> None:
        row = self.board.cursor.y + 1
        col = self.board.cursor.x + 1
        self.board.host.write(f"\033[{row};{col}R", flush=True)

    def report_device_status(self, operation: Operation) -> None:
        self.board.host.write("\033[0n", flush=True)

    def report_primary_device_attributes(self, operation: Operation) -> None:
        self.board.host.write(self.board.model.da1_response, flush=True)

    def report_secondary_device_attributes(self, operation: Operation) -> None:
        response = self.board.model.da2_response
        if response is not None:
            self.board.host.write(response, flush=True)

    def report_tertiary_device_attributes(self, operation: Operation) -> None:
        response = self.board.model.da3_response
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
            return f"{self.board.blitter.scroll_top + 1};{self.board.blitter.scroll_bottom + 1}r"
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
            return  # ignore malformed base64
        self.board.present(ClipboardChanged(sel, self.board.clipboard[sel]))

    def handle_window_op(self, operation: Operation) -> None:
        """XTWINOPS — window manipulation requests and reports; a frontend actuates them."""
        params = operation.args[0]

        def at(i: int) -> int:
            return params[i] if len(params) > i and params[i] is not None else 0

        op = at(0)
        board = self.board
        if op == 1:  # de-iconify
            board.window_iconified = False
            self._present_window_state()
        elif op == 2:  # iconify
            board.window_iconified = True
            self._present_window_state()
        elif op == 3:  # move window to (x, y)
            board.window_position = (at(1), at(2))
            self._present_window_state()
        elif op in (5, 6, 7):  # raise / lower / refresh
            kind = {5: "raise", 6: "lower", 7: "refresh"}[op]
            board.window_requests.append(kind)
            board.present(WindowRequest(kind))
        elif op == 8 and len(params) >= 3:  # resize text area to rows;cols
            board.resize(params[2] or board.width, params[1] or board.height)
        elif op == 9:  # maximize (0 restore, 1 maximize)
            board.window_maximized = at(1) == 1
            self._present_window_state()
        elif op == 10:  # fullscreen (0 off, 1 on, 2 toggle)
            board.window_fullscreen = (not board.window_fullscreen) if at(1) == 2 else at(1) == 1
            self._present_window_state()
        elif op == 11:  # report iconify state
            board.host.write(f"\x1b[{2 if board.window_iconified else 1}t", flush=True)
        elif op == 13:  # report window position
            x, y = board.window_position
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
            board.host.write(f"\x1b]L{board.title.icon_title}\x1b\\", flush=True)
        elif op == 21:  # report window title
            board.host.write(f"\x1b]l{board.title.title}\x1b\\", flush=True)
        elif op == 22:  # save title to the stack
            board.title.push()
        elif op == 23:  # restore title from the stack
            board.title.pop()
        elif op >= 24:  # DECSLPP — resize to Ps (>= 24) lines
            board.resize(board.width, op)

    def _present_window_state(self) -> None:
        board = self.board
        self.board.present(
            WindowStateChanged(
                board.window_iconified, board.window_maximized, board.window_fullscreen, board.window_position
            )
        )

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
            board.present(ConsoleRequest("switch", arg))
        elif op == 13:
            board.screen_blanked = False
        elif op == 14:
            board.vesa_powerdown = arg
        elif op == 15:
            board.console_requests.append(("previous", 0))
            board.present(ConsoleRequest("previous", 0))
        elif op == 16:
            board.cursor_blink_ms = arg

    def request_checksum(self, operation: Operation) -> None:
        """DECRQCRA — reply DCS Pid ! ~ HHHH ST with a 16-bit checksum of a rectangle.

        This is the DEC character-value form: the negated sum of the codepoints in
        the area, masked to 16 bits. (xterm can fold SGR attributes in too; that is a
        model detail we can add when a terminal needs it.)
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
        buffer = self.board.blitter.current_buffer
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
        """The capability strings this model answers XTGETTCAP with."""
        model = self.board.model
        colors = {"monochrome": "2", "16": "16", "256": "256", "truecolor": "256"}.get(model.color_depth, "256")
        caps = {"TN": model.name, "Co": colors, "colors": colors}
        if model.color_depth == "truecolor":
            caps["RGB"] = "8/8/8"
        return caps
