"""Screen and editing operation handlers for the current Terminal state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dataclasses import replace

from .. import constants
from ..buffer import Buffer
from .base import Device
from ..style import Style, parse_sgr_sequence

_REVERSE_ATTRS = {1: "bold", 4: "underline", 5: "blink", 7: "reverse"}

if TYPE_CHECKING:
    from .board import TerminalBoard


class ScreenDevice(Device):
    """Owns screen buffers and applies screen/editing operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.primary_buffer = Buffer(board.width, board.height)
        self.alt_buffer = Buffer(board.width, board.height)
        self.current_buffer = self.primary_buffer
        self.in_alt_screen = False
        self.scroll_top = 0
        self.scroll_bottom = board.height - 1
        self.last_printed_char = " "
        self.handlers = {
            "ED": lambda op: self.clear_screen(op.args[0]),
            "EL": lambda op: self.clear_line(op.args[0]),
            "DECSED": lambda op: self.selective_erase_display(op.args[0]),
            "DECSEL": lambda op: self.selective_erase_line(op.args[0]),
            "DECFRA": lambda op: self.fill_rectangle(op.args[0]),
            "DECERA": lambda op: self.erase_rectangle(op.args[0]),
            "DECSERA": lambda op: self.selective_erase_rectangle(op.args[0]),
            "DECCRA": lambda op: self.copy_rectangle(op.args[0]),
            "DECCARA": lambda op: self.change_attributes_rectangle(op.args[0]),
            "DECRARA": lambda op: self.reverse_attributes_rectangle(op.args[0]),
            "IL": lambda op: self.insert_lines(op.args[0]),
            "DL": lambda op: self.delete_lines(op.args[0]),
            "ICH": lambda op: self.insert_characters(op.args[0], self.board.style.current),
            "DCH": lambda op: self.delete_characters(op.args[0]),
            "ECH": lambda op: self.erase_characters(op.args[0]),
            "SU": lambda op: self.scroll(op.args[0]),
            "SD": lambda op: self.scroll(-op.args[0]),
            "SL": lambda op: self.pan(op.args[0]),
            "SR": lambda op: self.pan(-op.args[0]),
            "DECIC": lambda op: self.shift_columns(op.args[0]),
            "DECDC": lambda op: self.shift_columns(-op.args[0]),
            "REP": lambda op: self.repeat_last_character(op.args[0]),
            "DECSTBM": lambda op: self.set_top_and_bottom_margins(*op.args),
            "RIS": lambda op: self.board.reset(hard=True),
            "DECSTR": lambda op: self.board.reset(hard=False),
            "DECALN": lambda op: self.alignment_test(),
            "DECDHL_TOP": lambda op: self.set_line_attribute(constants.LINE_DOUBLE_TOP),
            "DECDHL_BOTTOM": lambda op: self.set_line_attribute(constants.LINE_DOUBLE_BOTTOM),
            "DECDWL": lambda op: self.set_line_attribute(constants.LINE_DOUBLE_WIDTH),
            "DECSWL": lambda op: self.set_line_attribute(constants.LINE_SINGLE),
        }

    def set_line_attribute(self, attribute: str) -> None:
        """DECDHL/DECDWL/DECSWL — set the cursor line's width/height attribute."""
        self.current_buffer.set_line_attribute(self.board.cursor.y, attribute)

    def write_text(self, text: str, ansi_code: str = "") -> None:
        """Write printable text at the cursor position."""
        self.board.cursor.prepare_for_text_write()

        code_to_use = ansi_code if ansi_code else self.board.style.current
        translated_text = self.board.charset.translate(text)

        if self.board.modes.insert_mode:
            self.current_buffer.insert(
                self.board.cursor.x,
                self.board.cursor.y,
                translated_text,
                code_to_use,
            )
        else:
            self.current_buffer.set(
                self.board.cursor.x,
                self.board.cursor.y,
                translated_text,
                code_to_use,
            )

        self.board.cursor.advance_after_text_write(len(translated_text))

        if translated_text:
            self.last_printed_char = translated_text[-1]

    def repeat_last_character(self, count: int) -> None:
        """Repeat the last printed character count times."""
        if count > 0 and self.last_printed_char:
            self.write_text(self.last_printed_char * count)

    def resize(self, width: int, height: int) -> None:
        """Resize terminal dimensions and screen buffers."""
        self.board.width = width
        self.board.height = height

        self.primary_buffer.resize(width, height)
        self.alt_buffer.resize(width, height)
        self.scroll_bottom = height - 1

        self.board.cursor.clamp_to_terminal()

    def clear_screen(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear screen."""
        bg_ansi = self.board.style.background_ansi()

        if mode == constants.ERASE_FROM_CURSOR_TO_END:
            self.current_buffer.clear_line(
                self.board.cursor.y,
                constants.ERASE_FROM_CURSOR_TO_END,
                self.board.cursor.x,
                bg_ansi,
            )
            for y in range(self.board.cursor.y + 1, self.board.height):
                self.current_buffer.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            for y in range(self.board.cursor.y):
                self.current_buffer.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
            self.clear_line(constants.ERASE_FROM_START_TO_CURSOR)
        elif mode == constants.ERASE_ALL:
            for y in range(self.board.height):
                self.current_buffer.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
            self.board.cursor.set_position(0, 0)

    def clear_line(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear line."""
        bg_ansi = self.board.style.background_ansi()
        self.current_buffer.clear_line(self.board.cursor.y, mode, self.board.cursor.x, bg_ansi)

    def clear_rect(self, x1: int, y1: int, x2: int, y2: int, ansi_code: str = "") -> None:
        """Clear a rectangular region."""
        self.current_buffer.clear_region(x1, y1, x2, y2, ansi_code)

    def _selective_clear(self, x: int, y: int) -> None:
        """Clear a cell only if it is not DECSCA-protected."""
        if not self.current_buffer.get_cell(x, y)[0].protected:
            self.current_buffer.set_cell(x, y, " ", self.board.style.background_ansi())

    def selective_erase_display(self, mode: int) -> None:
        """DECSED — erase in display, leaving DECSCA-protected characters."""
        cx, cy, w, h = self.board.cursor.x, self.board.cursor.y, self.board.width, self.board.height
        if mode == constants.ERASE_FROM_CURSOR_TO_END:
            rows = [(cx, w, cy)] + [(0, w, y) for y in range(cy + 1, h)]
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            rows = [(0, w, y) for y in range(cy)] + [(0, cx + 1, cy)]
        else:  # ERASE_ALL
            rows = [(0, w, y) for y in range(h)]
        for x0, x1, y in rows:
            for x in range(x0, x1):
                self._selective_clear(x, y)

    def selective_erase_line(self, mode: int) -> None:
        """DECSEL — erase in line, leaving DECSCA-protected characters."""
        cx, cy, w = self.board.cursor.x, self.board.cursor.y, self.board.width
        if mode == constants.ERASE_FROM_CURSOR_TO_END:
            span = range(cx, w)
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            span = range(cx + 1)
        else:  # ERASE_ALL
            span = range(w)
        for x in span:
            self._selective_clear(x, cy)

    # --- rectangular-area functions --- #

    def _rectangle(self, top, left, bottom, right) -> tuple[int, int, int, int]:
        """Clamp 1-based top/left/bottom/right (None/0 = extremes) to 0-based inclusive bounds."""
        t = (top - 1) if top else 0
        left0 = (left - 1) if left else 0
        b = (bottom - 1) if bottom else (self.board.height - 1)
        r = (right - 1) if right else (self.board.width - 1)
        t = max(0, min(t, self.board.height - 1))
        b = max(t, min(b, self.board.height - 1))
        left0 = max(0, min(left0, self.board.width - 1))
        r = max(left0, min(r, self.board.width - 1))
        return t, left0, b, r

    @staticmethod
    def _four(params, start=0):
        p = list(params) + [None] * (start + 4)
        return p[start], p[start + 1], p[start + 2], p[start + 3]

    def fill_rectangle(self, params) -> None:
        """DECFRA — fill a rectangle with a character (Pch;Pt;Pl;Pb;Pr)."""
        char = chr(params[0]) if params and params[0] else " "
        t, left, b, r = self._rectangle(*self._four(params, 1))
        for y in range(t, b + 1):
            for x in range(left, r + 1):
                self.current_buffer.set_cell(x, y, char, self.board.style.current)

    def erase_rectangle(self, params) -> None:
        """DECERA — erase a rectangle (Pt;Pl;Pb;Pr)."""
        t, left, b, r = self._rectangle(*self._four(params))
        bg = self.board.style.background_ansi()
        for y in range(t, b + 1):
            for x in range(left, r + 1):
                self.current_buffer.set_cell(x, y, " ", bg)

    def selective_erase_rectangle(self, params) -> None:
        """DECSERA — erase a rectangle, leaving DECSCA-protected characters."""
        t, left, b, r = self._rectangle(*self._four(params))
        for y in range(t, b + 1):
            for x in range(left, r + 1):
                self._selective_clear(x, y)

    def copy_rectangle(self, params) -> None:
        """DECCRA — copy a rectangle to another origin (Pts;Pls;Pbs;Prs;Pps;Ptd;Pld;Ppd)."""
        t, left, b, r = self._rectangle(*self._four(params))
        p = list(params) + [None] * 8
        dt = (p[5] - 1) if p[5] else 0
        dl = (p[6] - 1) if p[6] else 0
        cells = [[self.current_buffer.get_cell(x, y) for x in range(left, r + 1)] for y in range(t, b + 1)]
        for dy, row in enumerate(cells):
            for dx, cell in enumerate(row):
                ty, tx = dt + dy, dl + dx
                if 0 <= ty < self.board.height and 0 <= tx < self.board.width:
                    self.current_buffer.set_cell(tx, ty, cell[1], cell[0])

    def change_attributes_rectangle(self, params) -> None:
        """DECCARA — merge SGR attributes into every cell of a rectangle."""
        t, left, b, r = self._rectangle(*self._four(params))
        sgr = [str(x) for x in params[4:] if x is not None]
        delta = parse_sgr_sequence("\x1b[" + ";".join(sgr) + "m") if sgr else Style()
        for y in range(t, b + 1):
            for x in range(left, r + 1):
                cell = self.current_buffer.get_cell(x, y)
                self.current_buffer.set_cell(x, y, cell[1], cell[0].merge(delta))

    def reverse_attributes_rectangle(self, params) -> None:
        """DECRARA — toggle the given attributes (1/4/5/7) across a rectangle."""
        t, left, b, r = self._rectangle(*self._four(params))
        requested = [p for p in params[4:] if p in _REVERSE_ATTRS] or list(_REVERSE_ATTRS)
        attrs = [_REVERSE_ATTRS[p] for p in requested]
        for y in range(t, b + 1):
            for x in range(left, r + 1):
                cell = self.current_buffer.get_cell(x, y)
                style = cell[0]
                for attr in attrs:
                    style = replace(style, **{attr: not getattr(style, attr)})
                self.current_buffer.set_cell(x, y, cell[1], style)

    def switch_screen(self, alt: bool) -> None:
        """Switch between primary and alternate screen."""
        if alt and not self.in_alt_screen:
            self.current_buffer = self.alt_buffer
            self.in_alt_screen = True
        elif not alt and self.in_alt_screen:
            self.current_buffer = self.primary_buffer
            self.in_alt_screen = False

    def alignment_test(self) -> None:
        """Fill the screen with 'E' characters for alignment testing."""
        test_text = "E" * self.board.width
        for y in range(self.board.height):
            self.current_buffer.set(0, y, test_text)

    def set_scroll_region(self, top: int, bottom: int) -> None:
        """Set scroll region."""
        self.scroll_top = max(0, min(top, self.board.height - 1))
        self.scroll_bottom = max(self.scroll_top, min(bottom, self.board.height - 1))

    def set_top_and_bottom_margins(self, top: int, bottom: int | None) -> None:
        """DECSTBM — set the scroll region and home the cursor (origin-aware)."""
        self.set_scroll_region(top, self.board.height - 1 if bottom is None else bottom)
        self.board.cursor.move_to(0, 0)

    def insert_lines(self, count: int) -> None:
        """Insert blank lines at cursor position."""
        if count <= 0 or not (self.scroll_top <= self.board.cursor.y <= self.scroll_bottom):
            return

        self.current_buffer.scroll_region_down(self.board.cursor.y, self.scroll_bottom, count)

    def delete_lines(self, count: int) -> None:
        """Delete lines at cursor position."""
        if count <= 0 or not (self.scroll_top <= self.board.cursor.y <= self.scroll_bottom):
            return

        self.current_buffer.scroll_region_up(self.board.cursor.y, self.scroll_bottom, count)

    def insert_characters(self, count: int, ansi_code: str = "") -> None:
        """Insert blank characters at cursor position."""
        if not (0 <= self.board.cursor.y < self.board.height):
            return
        spaces = " " * count
        self.current_buffer.insert(self.board.cursor.x, self.board.cursor.y, spaces, ansi_code)

    def delete_characters(self, count: int) -> None:
        """Delete characters at cursor position."""
        if not (0 <= self.board.cursor.y < self.board.height):
            return
        self.current_buffer.delete(self.board.cursor.x, self.board.cursor.y, count)

    def scroll(self, lines: int) -> None:
        """Scroll content within the active scroll region."""
        if lines == 0 or self.scroll_top > self.scroll_bottom:
            return

        abs_lines = abs(lines)
        if lines > 0:
            self.current_buffer.scroll_region_up(self.scroll_top, self.scroll_bottom, abs_lines)
        else:
            self.current_buffer.scroll_region_down(self.scroll_top, self.scroll_bottom, abs_lines)

    def pan(self, columns: int) -> None:
        """Pan the scroll-region rows horizontally: SL (columns > 0) left, SR (< 0) right."""
        if columns == 0 or self.scroll_top > self.scroll_bottom:
            return
        width = self.board.width
        n = min(abs(columns), width)
        bg = self.board.style.background_ansi()
        for y in range(self.scroll_top, self.scroll_bottom + 1):
            row = [self.current_buffer.get_cell(x, y) for x in range(width)]
            shifted = row[n:] + [None] * n if columns > 0 else [None] * n + row[: width - n]
            for x, cell in enumerate(shifted):
                if cell is None:
                    self.current_buffer.set_cell(x, y, " ", bg)
                else:
                    self.current_buffer.set_cell(x, y, cell[1], cell[0])

    def shift_columns(self, count: int) -> None:
        """Insert (count > 0, DECIC) or delete (count < 0, DECDC) columns at the cursor.

        Operates on every row within the vertical scroll region; cells shift within
        the line and the vacated columns are blanked with the current background.
        """
        if count == 0 or self.scroll_top > self.scroll_bottom:
            return
        x0 = self.board.cursor.x
        width = self.board.width
        n = min(abs(count), width - x0)
        bg = self.board.style.background_ansi()
        for y in range(self.scroll_top, self.scroll_bottom + 1):
            row = [self.current_buffer.get_cell(x, y) for x in range(width)]
            if count > 0:  # insert blanks at x0, pushing the tail right
                tail = [None] * n + row[x0 : width - n]
            else:  # delete at x0, pulling the tail left, blanks at the right edge
                tail = row[x0 + n :] + [None] * n
            for i, cell in enumerate(tail):
                if cell is None:
                    self.current_buffer.set_cell(x0 + i, y, " ", bg)
                else:
                    self.current_buffer.set_cell(x0 + i, y, cell[1], cell[0])

    def scroll_up(self, count: int) -> None:
        """Scroll content up within scroll region."""
        self.scroll(count)

    def scroll_down(self, count: int) -> None:
        """Scroll content down within scroll region."""
        self.scroll(-count)

    def reset(self, hard: bool = True) -> None:
        """Restore the full scroll region; a hard reset also clears both buffers to primary."""
        self.set_scroll_region(0, self.board.height - 1)
        if not hard:
            return
        self.in_alt_screen = False
        self.current_buffer = self.primary_buffer
        for buf in (self.primary_buffer, self.alt_buffer):
            buf.reset_line_attributes()
            for y in range(self.board.height):
                buf.clear_line(y, constants.ERASE_ALL, 0, "")
        self.last_printed_char = " "

    def set_column_mode(self, columns: int) -> None:
        """Set terminal width for DECCOLM."""
        if columns not in (80, 132):
            return
        if self.board.width == columns:
            return

        self.resize(columns, self.board.height)
        self.board.cursor.set_position(0, 0)

    def erase_characters(self, count: int) -> None:
        """Erase `count` characters from the cursor with the current style (ECH)."""
        for _ in range(count):
            self.current_buffer.set(
                self.board.cursor.x,
                self.board.cursor.y,
                " ",
                self.board.style.current,
            )
            if self.board.cursor.x < self.board.width - 1:
                self.board.cursor.x += 1
