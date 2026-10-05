"""Query operation handler for the current board state."""

from __future__ import annotations

import re

from typing import TYPE_CHECKING

from .. import constants
from ..operations import Operation
from ..options import (
    DEC_DISPLAYED_EXTENT,
    DEC_EXTENDED_CPR,
    DEC_STATUS_LINE,
    DEC_TERMINAL_STATE,
    DEC_UPSS,
    XTERM_EXTRAS,
)
from ..parser import Parser
from ..style import common_style, style_to_ansi
from .base import Device

if TYPE_CHECKING:
    from .board import Board


# style_to_ansi writes extended colours in their semicolon forms.
_INDEXED_COLOR = re.compile(r"\b([345]8);5;(\d+)")
_DIRECT_COLOR = re.compile(r"\b([345]8);2;(\d+);(\d+);(\d+)")


def _bit_field(*flags) -> str:
    """A DEC report's flag character: 0x40 plus bit n for each set flag n."""
    return chr(0x40 | sum(1 << bit for bit, on in enumerate(flags) if on))


def _flags_of(field: int, count: int) -> tuple[bool | None, ...]:
    """The first count flags of a report's bit field, as style flags (True or None)."""
    return tuple(True if field >> bit & 1 else None for bit in range(count))


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
            "DECRQPSR": self.report_presentation_state,
            "DECRSPS_CIR": self.restore_cursor_information,
            "DECRSPS_TABS": lambda op: setattr(
                board.cursor, "tab_stops", {stop - 1 for stop in op.args[0] if 0 < stop <= board.width}
            ),
            "DECSCL": self.set_conformance_level,
            "DECRQCRA": self.request_checksum,
            "XTGETTCAP": self.request_termcap,
            "XTVERSION": self.report_version,
        }
        # DECRQSS: each setting's current parameters, answered with the request as final.
        blitter = board.blitter
        self._status_reporters = {
            "m": self._sgr_status,
            "r": lambda: f"{blitter.scroll_top + 1};{blitter.scroll_bottom + 1}",
            "s": lambda: f"{blitter.left_margin + 1};{blitter.right_margin + 1}",
            "t": lambda: str(self.board.height),  # DECSLPP
            "*|": lambda: str(self.board.height),  # DECSNLS
            "$|": lambda: str(self.board.width),  # DECSCPP
            " q": self._cursor_style_status,
            '"q': lambda: "1" if self.board.style.current.protected else "0",  # DECSCA
            '"p': lambda: f"{self.board.conformance_level};{0 if self.board.c1_eightbit else 1}",
            "*x": lambda: "2" if blitter.attr_change_extent == "rectangle" else "0",
        }
        if XTERM_EXTRAS in board.model.provides:
            self.handlers["XTREPORTSGR"] = self.report_rendition
            self._status_reporters[">t"] = lambda: ";".join(str(int(mode)) for mode in board.title.modes)
        if DEC_DISPLAYED_EXTENT in board.model.provides:
            self.handlers["DECRQDE"] = self.report_displayed_extent
        if DEC_EXTENDED_CPR in board.model.provides:
            self.handlers["DECXCPR"] = self.report_extended_cursor_position
        if DEC_TERMINAL_STATE in board.model.provides:
            self.handlers["DECRQTSR"] = self.report_terminal_state
            self.handlers["DECRSTS"] = self.restore_terminal_state
        if DEC_STATUS_LINE in board.model.provides:
            self._status_reporters["$~"] = lambda: str(blitter.status_type)  # DECSSDT
            self._status_reporters["$}"] = lambda: str(int(blitter.status_active))  # DECSASD

    def report_version(self, operation: Operation) -> None:
        """XTVERSION (CSI > q) — reply DCS > | name version ST."""
        self.board.host.write(f"\x1bP>|bittty({constants.VERSION})\x1b\\", flush=True)

    def report_cursor_position(self, operation: Operation) -> None:
        row = self.board.cursor.y + 1
        col = self.board.cursor.display_x + 1
        self.board.host.write(f"\033[{row};{col}R", flush=True)

    def report_extended_cursor_position(self, operation: Operation) -> None:
        """DECXCPR — the cursor position and the page it is on."""
        row = self.board.cursor.y + 1
        col = self.board.cursor.display_x + 1
        self.board.host.write(f"\033[?{row};{col};{self.board.blitter.page_number}R", flush=True)

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
        status = self.modes.mode_status(private, mode)
        prefix = "?" if private else ""
        self.board.host.write(f"\033[{prefix}{mode};{status}$y", flush=True)

    def report_status_string(self, operation: Operation) -> None:
        """DECRQSS — answer a request for the current value of a setting."""
        request = operation.args[0]
        setting = self._status_string(request)
        board = self.board
        settings = (
            (setting,)
            if setting is not None
            else board.comm.status_strings(request) or board.printer.status_strings(request)
        )
        valid = "1" if self.board.model.decrqss_valid_is_one else "0"
        invalid = "0" if self.board.model.decrqss_valid_is_one else "1"
        if settings is not None:
            for value in settings:
                self.board.host.write(f"\x1bP{valid}$r{value}\x1b\\", flush=True)
            return
        # Modern emulators echo the unsupported request. DEC hardware emits no
        # setting data in the invalid response.
        suffix = request if self.board.model.decrqss_valid_is_one else ""
        self.board.host.write(f"\x1bP{invalid}$r{suffix}\x1b\\", flush=True)

    def _status_string(self, request: str) -> str | None:
        """A setting's parameters between the request's private marker and its final characters."""
        reporter = self._status_reporters.get(request)
        if reporter is None:
            return None
        marker = request[0] if request[0] in "<=>?" else ""
        return marker + reporter() + request[len(marker) :]

    def _sgr_status(self) -> str:
        return self._rendition(self.board.style.current)

    def report_rendition(self, operation: Operation) -> None:
        """XTREPORTSGR — the rendition every cell of a rectangle shares, as an SGR."""
        styles = self.board.blitter.rectangle_styles(operation.args[0])
        self.board.host.write(f"\x1b[{self._rendition(common_style(styles))}m", flush=True)

    @staticmethod
    def _rendition(style) -> str:
        """A rendition as xterm reports it: reset first, colours from 16 up in their colon forms."""
        ansi = style_to_ansi(style)
        params = _INDEXED_COLOR.sub(r"\1:5:\2", _DIRECT_COLOR.sub(r"\1:2::\2:\3:\4", ansi[2:-1]))
        return f"0;{params}" if params else "0"

    def _cursor_style_status(self) -> str:
        base = {"block": 1, "underline": 3, "bar": 5}.get(self.board.cursor.shape, 1)
        return str(base if self.board.modes.cursor_blinking else base + 1)

    def report_displayed_extent(self, operation: Operation) -> None:
        """DECRQDE — the display's size, its top-left in page memory (always 1;1: no panning) and page."""
        board = self.board
        page = 1 if board.blitter.in_alt_screen else board.blitter.shown_page + 1
        board.host.write(f'\x1b[{board.height};{board.width};1;1;{page}"w', flush=True)

    def report_terminal_state(self, operation: Operation) -> None:
        """DECRQTSR 1 — DECTSR: the hex of the control functions that re-establish this state."""
        if operation.args[0] == 1:
            data = self._terminal_state().encode().hex().upper()
            self.board.host.write(f"\x1bP1$s{data}\x1b\\", flush=True)

    def _terminal_state(self) -> str:
        """Modes, margins, renditions and settings, then the cursor and tab stops (restored last:
        setting origin mode or a margin homes the cursor)."""
        board, blitter = self.board, self.board.blitter
        modes = board.modes.restorable_states()
        parts = [f"\x1b[{'?' * private}{number}{'hl'[not on]}" for private, number, on in modes]
        parts.append(f"\x1b[{blitter.scroll_top + 1};{blitter.scroll_bottom + 1}r")
        if board.modes.left_right_margin_mode:
            parts.append(f"\x1b[{blitter.left_margin + 1};{blitter.right_margin + 1}s")
        parts.append(f"\x1b[{2 if blitter.attr_change_extent == 'rectangle' else 0}*x")
        parts.append(f"\x1b[{self._cursor_style_status()} q\x1b[{self._sgr_status()}m")
        if DEC_STATUS_LINE in board.model.provides:
            parts.append(f"\x1b[{blitter.status_type}$~")
        if DEC_UPSS in board.model.provides:
            parts.append(board.charset.preferred_assignment())
        parts.append(f"\x1bP1$t{self._cursor_information()}\x1b\\\x1bP2$t{self._tab_stops()}\x1b\\")
        return "".join(parts)

    def restore_terminal_state(self, operation: Operation) -> None:
        """DECRSTS 1 — replay a DECTSR; one that is not hex is ignored whole."""
        try:
            data = bytes.fromhex(operation.args[0]).decode()
        except ValueError:
            return
        Parser(self.board).feed(data)

    def report_presentation_state(self, operation: Operation) -> None:
        """DECRQPSR — cursor information (1, DECCIR) or tab stops (2, DECTABSR); anything else is ignored."""
        ps = operation.args[0]
        reporter = {1: self._cursor_information, 2: self._tab_stops}.get(ps)
        if reporter:
            self.board.host.write(f"\x1bP{ps}$u{reporter()}\x1b\\", flush=True)

    def _cursor_information(self) -> str:
        """DECCIR: position, page, rendition, protection, flags, invoked and designated G-sets."""
        board, cursor, charset = self.board, self.board.cursor, self.board.charset
        style = board.style.current
        srend = _bit_field(style.bold, style.underline, style.blink, style.reverse)
        satt = _bit_field(style.protected)
        sflag = _bit_field(
            board.modes.origin_mode, charset.single_shift == 2, charset.single_shift == 3, cursor.wrap_pending
        )
        scss = _bit_field(*(designation.startswith("96") for designation in charset.charset_array))
        designations = "".join(designation.removeprefix("96") for designation in charset.charset_array)
        position = f"{cursor.y + 1};{cursor.display_x + 1};{board.blitter.page_number}"
        shifts = f"{charset.current_charset};{charset.gr}"
        return f"{position};{srend};{satt};{sflag};{shifts};{scss};{designations}"

    def restore_cursor_information(self, operation: Operation) -> None:
        """DECRSPS 1 — restore a DECCIR report; one placing the cursor off the screen is rejected whole."""
        row, column, page, srend, satt, sflag, gl, gr, scss, designators = operation.args
        board, cursor, charset = self.board, self.board.cursor, self.board.charset
        if not (0 < row <= board.height and 0 < column <= board.width):
            return
        board.blitter.move_to_page(page - 1)
        board.modes.set_mode(6, bool(sflag & 1), private=True)  # DECOM first: setting it homes the cursor
        cursor.set_position(column - 1, row - 1)
        if sflag & 8:
            cursor.arm_pending_wrap()
        bold, underline, blink, reverse = _flags_of(srend, 4)
        board.style.current = board.style.current.replace(
            bold=bold, underline=underline, blink=blink, reverse=reverse, protected=_flags_of(satt, 1)[0]
        )
        charset.single_shift = {2: 2, 4: 3}.get(sflag & 6)
        charset.current_charset, charset.gr = gl, gr
        for index, (designator, is_96) in enumerate(zip(designators[:4], _flags_of(scss, 4))):
            charset.designate(index, ("96" if is_96 else "") + designator)

    def _tab_stops(self) -> str:
        """DECTABSR: the tab stop columns, one-based and separated by '/'."""
        return "/".join(str(stop + 1) for stop in sorted(self.board.cursor.tab_stops))

    def set_conformance_level(self, operation: Operation) -> None:
        """DECSCL — record the conformance level and C1 transmission (behaviourally a no-op).

        As in xterm, a VT200-or-later level selects 8-bit controls unless the second parameter is 1.
        """
        params = operation.args[0]
        self.board.blitter.select_active_display(False)  # DECSCL leaves the status line (VT510)
        if params and params[0] is not None:
            self.board.conformance_level = params[0]
            self.board.c1_eightbit = params[0] > 61 and (*params, None)[1] != 1

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
        page = self.board.blitter.page_at(at(1, 1))
        total = 0
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                char = page.get_cell(x, y)[1]
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
        caps = {"TN": model.term_name or model.name, "Co": colors, "colors": colors}
        if model.color_depth == "truecolor":
            caps["RGB"] = "8/8/8"
        return caps
