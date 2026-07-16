"""Screen and editing operation handlers for the current Terminal state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dataclasses import replace

from .. import constants
from ..buffer import Buffer
from ..operations import Operation
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
        self.left_margin = 0
        self.right_margin = board.width - 1
        self.attr_change_extent = "rectangle"  # DECSACE: "rectangle" or "stream"
        self.last_printed_char = " "
        self.handlers = {
            "DECSLRM": self.apply_left_right_margins,
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
            "DECSACE": lambda op: self.set_attr_change_extent(op.args[0]),
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
        self.reset_left_right_margins()

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

    def set_attr_change_extent(self, ps: int) -> None:
        """DECSACE — 1 = stream (wrapping run), else rectangle (default)."""
        self.attr_change_extent = "stream" if ps == 1 else "rectangle"

    def _extent_cells(self, params):
        """Yield (x, y) cells for DECCARA/DECRARA per DECSACE: a rectangle, or a wrapping stream."""
        top, left, bottom, right = self._four(params)
        if self.attr_change_extent == "stream":
            # Raw corners, clamped to the screen but not normalised (the end may precede the start).
            h, w = self.board.height, self.board.width
            t = max(0, min((top - 1) if top else 0, h - 1))
            left0 = max(0, min((left - 1) if left else 0, w - 1))
            b = max(0, min((bottom - 1) if bottom else h - 1, h - 1))
            r = max(0, min((right - 1) if right else w - 1, w - 1))
            for pos in range(t * w + left0, b * w + r + 1):
                y, x = divmod(pos, w)
                if 0 <= y < h:
                    yield x, y
        else:
            t, left0, b, r = self._rectangle(top, left, bottom, right)
            for y in range(t, b + 1):
                for x in range(left0, r + 1):
                    yield x, y

    def change_attributes_rectangle(self, params) -> None:
        """DECCARA — merge SGR attributes into every cell of the area (rectangle or stream)."""
        sgr = [str(x) for x in params[4:] if x is not None]
        delta = parse_sgr_sequence("\x1b[" + ";".join(sgr) + "m") if sgr else Style()
        for x, y in self._extent_cells(params):
            cell = self.current_buffer.get_cell(x, y)
            self.current_buffer.set_cell(x, y, cell[1], cell[0].merge(delta))

    def reverse_attributes_rectangle(self, params) -> None:
        """DECRARA — toggle the given attributes (1/4/5/7) across the area (rectangle or stream)."""
        requested = [p for p in params[4:] if p in _REVERSE_ATTRS] or list(_REVERSE_ATTRS)
        attrs = [_REVERSE_ATTRS[p] for p in requested]
        for x, y in self._extent_cells(params):
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

    def _shift_row_segment(self, x0: int, columns: int) -> None:
        """Shift the [x0, right_margin] cells of every scroll-region row by columns.

        columns > 0 pushes content left (blanks appear on the right of the segment);
        columns < 0 pushes it right. Vacated cells take the current background.
        """
        if columns == 0 or self.scroll_top > self.scroll_bottom:
            return
        right = self.right_margin
        span = right - x0 + 1
        if span <= 0:
            return
        n = min(abs(columns), span)
        bg = self.board.style.background_ansi()
        for y in range(self.scroll_top, self.scroll_bottom + 1):
            seg = [self.current_buffer.get_cell(x, y) for x in range(x0, right + 1)]
            seg = seg[n:] + [None] * n if columns > 0 else [None] * n + seg[: span - n]
            for i, cell in enumerate(seg):
                if cell is None:
                    self.current_buffer.set_cell(x0 + i, y, " ", bg)
                else:
                    self.current_buffer.set_cell(x0 + i, y, cell[1], cell[0])

    def pan(self, columns: int) -> None:
        """SL/SR — pan the scroll-region rows horizontally within the left/right margins."""
        self._shift_row_segment(self.left_margin, columns)

    def shift_columns(self, count: int) -> None:
        """DECIC (count > 0) / DECDC (count < 0) — insert/delete columns at the cursor.

        Confined to the left/right margin box; a cursor outside it is a no-op.
        """
        x0 = self.board.cursor.x
        if not (self.left_margin <= x0 <= self.right_margin):
            return
        # DECIC inserts blanks at x0 (content pushed right = negative shift); DECDC deletes (left).
        self._shift_row_segment(x0, -count)

    def set_left_right_margins(self, left: int | None, right: int | None) -> None:
        """DECSLRM — set the left/right margins (1-based; None/0 = extremes) and home the cursor."""
        width = self.board.width
        left0 = (left - 1) if left else 0
        right0 = (right - 1) if right else (width - 1)
        left0 = max(0, min(left0, width - 1))
        right0 = max(left0, min(right0, width - 1))
        self.left_margin = left0
        self.right_margin = right0
        self.board.cursor.move_to(0, 0)

    def reset_left_right_margins(self) -> None:
        """Restore the margins to the full screen width."""
        self.left_margin = 0
        self.right_margin = self.board.width - 1

    def apply_left_right_margins(self, operation: Operation) -> None:
        """CSI Pl ; Pr s — DECSLRM when margin mode is on, else SCOSC (save cursor)."""
        if not self.board.modes.left_right_margin_mode:
            self.board.cursor.save()
            return
        params = operation.args[0]
        left = params[0] if params and params[0] is not None else None
        right = params[1] if len(params) > 1 and params[1] is not None else None
        self.set_left_right_margins(left, right)

    def scroll_up(self, count: int) -> None:
        """Scroll content up within scroll region."""
        self.scroll(count)

    def scroll_down(self, count: int) -> None:
        """Scroll content down within scroll region."""
        self.scroll(-count)

    def reset(self, hard: bool = True) -> None:
        """Restore the full scroll region; a hard reset also clears both buffers to primary."""
        self.set_scroll_region(0, self.board.height - 1)
        self.reset_left_right_margins()
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
