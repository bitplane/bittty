"""The blitter: writes video memory. Screen and editing operation handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import constants
from ..clusters import ClusterWriter
from ..operations import Operation
from ..options import DEC_CHARACTER_EDITING, DEC_LINE_EDITING, DEC_STATUS_LINE
from ..present import StatusLineChanged
from ..style import Style, parse_sgr_sequence
from ..video import Video
from .base import Device
from .modes import ModeEffect

_REVERSE_ATTRS = {1: "bold", 4: "underline", 5: "blink", 7: "reverse"}
_STATUS_LINE_KINDS = ("none", "indicator", "host-writable")  # DECSSDT 0-2

if TYPE_CHECKING:
    from ..width import WidthPolicy
    from .board import Board


class Blitter(Device):
    """Owns the video pages and applies screen/editing operations."""

    def __init__(self, board: Board) -> None:
        self.board = board
        # Page memory: the primary screen is one of these pages. `page` has the cursor and
        # `shown_page` is on display; they part only while DECPCCM is reset.
        self.pages = [Video(board.width, board.height, board.width_policy)]
        self.page = self.shown_page = 0
        self._fit_page_memory()
        self.alt_page = Video(board.width, board.height, board.width_policy)
        self.current_page = self.primary_page
        self.in_alt_screen = False
        self.scroll_top = 0
        self.scroll_bottom = board.height - 1
        self.left_margin = 0
        self.right_margin = board.width - 1
        self.attr_change_extent = "stream"  # DECSACE: "stream" (power-on) or "rectangle"
        self.last_printed_char = ""  # REP before any printing repeats nothing
        self._clusters = ClusterWriter(self)
        self.grapheme_clustering = False
        self.right_to_left = False  # DECRLM
        self._rtl_wrap_at: tuple[int, int] | None = None  # where a right-to-left line was filled
        # The status line (DECSSDT/DECSASD) is a one-row display of its own: while it is
        # active, writes go to status_page and the main display's context waits in _main.
        self.status_type = board.model.status_line_type
        self.status_page = Video(board.width, 1, board.width_policy)
        self.status_active = False
        self._main: tuple | None = None
        self._status_x = 0
        self.handlers = {
            "DECSLRM": self.apply_left_right_margins,
            "DECSCPP": lambda op: self.board.set_page_columns(op.args[0]),
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
        if DEC_LINE_EDITING in board.model.provides:
            self.handlers["IL"] = lambda op: self.insert_lines(op.args[0])
            self.handlers["DL"] = lambda op: self.delete_lines(op.args[0])
            self.handlers["DCH"] = lambda op: self.delete_characters(op.args[0])
        if DEC_CHARACTER_EDITING in board.model.provides:
            self.handlers["ICH"] = lambda op: self.insert_characters(op.args[0], self.board.style.current)
            self.handlers["ECH"] = lambda op: self.erase_characters(op.args[0])
        if board.model.page_memory:
            self.handlers.update(
                {
                    "NP": lambda op: self.move_to_page(self.page + op.args[0], home=True),
                    "PP": lambda op: self.move_to_page(self.page - op.args[0], home=True),
                    "PPA": lambda op: self.move_to_page(op.args[0] - 1),
                    "PPR": lambda op: self.move_to_page(self.page + op.args[0]),
                    "PPB": lambda op: self.move_to_page(self.page - op.args[0]),
                }
            )
        if DEC_STATUS_LINE in board.model.provides:
            self.handlers["DECSSDT"] = lambda op: self.select_status_type(op.args[0])
            self.handlers["DECSASD"] = lambda op: self.select_active_display(op.args[0] == 1)

    # --- page memory --- #

    @property
    def primary_page(self) -> Video:
        """The primary screen: the page of page memory the cursor is on."""
        return self.pages[self.page]

    @property
    def videos(self) -> tuple[Video, ...]:
        """Every full-screen page: page memory and the alternate screen."""
        return (*self.pages, self.alt_page)

    @property
    def main_page(self) -> Video:
        """The page the main display shows, even while writes go to the status line."""
        return self.alt_page if self.in_alt_screen else self.pages[self.shown_page]

    @property
    def page_number(self) -> int:
        """The one-based page the cursor is on, as reports give it; the alternate screen is page 1."""
        return 1 if self.in_alt_screen else self.page + 1

    @property
    def cursor_on_display(self) -> bool:
        """Whether the cursor is on the displayed page, rather than the status line or another page."""
        return not self.status_active and self.current_page is self.main_page

    def _fit_page_memory(self) -> None:
        """Hold as many pages as the model's memory has at this page size, keeping those that fit."""
        board = self.board
        count = board.model.pages_for(board.height)
        del self.pages[count:]
        self.pages += [Video(board.width, board.height, board.width_policy) for _ in range(count - len(self.pages))]
        self.page = min(self.page, count - 1)
        self.shown_page = min(self.shown_page, count - 1)

    def page_at(self, number: int | None) -> Video:
        """A page of memory by its one-based number (default and minimum 1, clamped to the last).

        On the alternate screen or the status line the page named is the one being written.
        """
        if self.in_alt_screen or self.status_active:
            return self.current_page
        return self.pages[min(max(number or 1, 1), len(self.pages)) - 1]

    def move_to_page(self, index: int, *, home: bool = False) -> None:
        """NP/PP (home) and PPA/PPR/PPB (same row and column): the cursor to another page.

        The index is clamped to page memory; with one page, or off the primary screen, nothing moves.
        """
        if len(self.pages) == 1 or self.in_alt_screen or self.status_active:
            return
        self.reset_grapheme_state()
        self.page = min(max(index, 0), len(self.pages) - 1)
        self.current_page = self.primary_page
        if self.board.modes.page_cursor_coupling:
            self.shown_page = self.page
        if home:
            self.board.cursor.move_to(0, 0)
        else:
            self.board.cursor.cancel_pending_wrap()

    def couple_display(self) -> None:
        """DECPCCM set: the display shows the cursor's page."""
        self.shown_page = self.page

    # --- status line --- #

    def select_status_type(self, kind: int) -> None:
        """DECSSDT — none (0), indicator (1) or host-writable (2); a new host-writable line is empty."""
        if kind not in (0, 1, 2) or kind == self.status_type:
            return
        if kind != 2:
            self.select_active_display(False)
        else:
            self.status_page.clear_line(0, constants.ERASE_ALL, 0, "")
        self.status_type = kind
        self.board.present(StatusLineChanged(_STATUS_LINE_KINDS[kind]))

    def select_active_display(self, status: bool) -> None:
        """DECSASD — send data to the host-writable status line, or back to the main display.

        The status line is a one-row display: only column positions operate there.
        """
        status = status and self.status_type == 2
        if status == self.status_active:
            return
        board, cursor = self.board, self.board.cursor
        self.reset_grapheme_state()
        here = (cursor.display_x, cursor.y, cursor.wrap_pending)
        if status:
            self._main = (self.current_page, board.height, self.scroll_top, self.scroll_bottom,
                          self.left_margin, self.right_margin, *here)  # fmt: skip
            self.current_page, board.height = self.status_page, 1
            self.scroll_top = self.scroll_bottom = self.left_margin = 0
            self.right_margin = board.width - 1
            x, y, wrap = self._status_x, 0, False
        else:
            self._status_x = here[0]
            (self.current_page, board.height, self.scroll_top, self.scroll_bottom,
             self.left_margin, self.right_margin, x, y, wrap) = self._main  # fmt: skip
        self.status_active = status
        cursor.set_position(x, y)
        if wrap:
            cursor.arm_pending_wrap()

    def set_line_attribute(self, attribute: str) -> None:
        """DECDHL/DECDWL/DECSWL — set the cursor line's width/height attribute."""
        if self.board.modes.left_right_margin_mode:
            return
        self.current_page.set_line_attribute(self.board.cursor.y, attribute)

    def write_text(self, text: str, ansi_code: str = "") -> None:
        """Write printable text at the cursor, accounting for terminal columns.

        ASCII runs keep the bulk slice path. Non-ASCII code points are measured
        by the board's width policy and width-2 characters are written
        atomically.
        """
        board = self.board
        code_to_use = ansi_code if ansi_code else board.style.current
        translated_text = board.charset.translate(text)
        cursor = board.cursor
        width = board.width

        def write_ascii_run(run: str) -> None:
            remaining = run
            while remaining:
                bounds = cursor.prepare_for_text_write()
                space = bounds[1] - cursor.x
                chunk, remaining = remaining[:space], remaining[space:]
                if board.modes.insert_mode:
                    self.current_page.insert(cursor.x, cursor.y, chunk, code_to_use, right=bounds[1])
                else:
                    self.current_page.set(cursor.x, cursor.y, chunk, code_to_use)
                cursor.advance_after_text_write(len(chunk), bounds)

        if translated_text.isascii():
            write_ascii_run(translated_text)
        else:
            start = 0
            for index, char in enumerate(translated_text):
                if char.isascii():
                    continue
                if start < index:
                    write_ascii_run(translated_text[start:index])

                char_width = board.width_policy.width(char)
                if char_width > width:
                    start = index + 1
                    continue

                bounds = cursor.prepare_for_text_write()
                if char_width > bounds[1] - cursor.x:
                    if board.modes.auto_wrap:
                        cursor.x = bounds[1]
                        cursor.mark_pending_wrap(bounds)
                        bounds = cursor.prepare_for_text_write()
                    else:
                        cursor.x = bounds[1] - char_width

                if board.modes.insert_mode:
                    self.current_page.insert(cursor.x, cursor.y, char, code_to_use, right=bounds[1])
                else:
                    self.current_page.set(cursor.x, cursor.y, char, code_to_use)
                cursor.advance_after_text_write(char_width, bounds)
                start = index + 1

            if start < len(translated_text):
                write_ascii_run(translated_text[start:])

        if translated_text:
            self.last_printed_char = translated_text[-1]

    def set_grapheme_clustering(self, enabled: bool) -> None:
        """Switch the write callable so disabled mode has no per-run branch."""
        self.reset_grapheme_state()
        self.grapheme_clustering = enabled
        self._select_writer()

    def set_right_to_left(self, enabled: bool) -> None:
        """DECRLM — text runs right to left, and CR and BS turn round with it."""
        self.reset_grapheme_state()
        self.right_to_left = enabled
        self._rtl_wrap_at = None
        self.board.cursor.set_right_to_left(enabled)
        self._select_writer()

    def _select_writer(self) -> None:
        """The write callable for the current direction and clustering, chosen once rather than per run."""
        self.__dict__.pop("write_text", None)
        if self.right_to_left:
            self.write_text = self._write_right_to_left
        elif self.grapheme_clustering:
            self.write_text = self._clusters.write

    def _write_right_to_left(self, text: str, ansi_code: str = "") -> None:
        """DECRLM: each character goes at the cursor, which then moves left (VT510).

        In insert mode the characters from the cursor to the left margin shift left first. A
        character printed at the left margin (or column 1, left of it) leaves the cursor there;
        the next one, under autowrap, starts the next line at the right margin. Characters are
        written one by one: grapheme clustering does not apply.
        """
        board, cursor = self.board, self.board.cursor
        style = ansi_code or board.style.current
        for char in board.charset.translate(text):
            width = board.width_policy.width(char)
            if not 0 < width <= board.width:
                continue
            if self._rtl_wrap_at == (cursor.x, cursor.y) and board.modes.auto_wrap:
                right = self.right_margin if cursor.x >= self.left_margin else board.width - 1
                cursor.line_feed(is_wrapped=True)
                cursor.x = right
            self._rtl_wrap_at = None
            left = self.left_margin if cursor.x >= self.left_margin else 0
            x = max(cursor.x - width + 1, left)
            if board.modes.insert_mode:
                self._shift_line_segment(cursor.y, left, cursor.x, width)
            self.current_page.set(x, cursor.y, char, style)
            if x == left:
                cursor.x = left
                self._rtl_wrap_at = (left, cursor.y)
            else:
                cursor.x = x - 1
            self.last_printed_char = char

    def reset_grapheme_state(self) -> None:
        """Forget streaming state without changing already-written cells."""
        self._clusters.reset()

    def repeat_last_character(self, count: int) -> None:
        """Repeat the last printed character count times.

        The count comes off the wire, so it is clamped before it becomes a
        string. Once a screenful of one character has been written the rows
        above are all that character whatever happens next, so only the
        alignment of the final partial row still matters — keeping the clamp
        congruent to the count modulo the width reproduces it exactly.
        """
        if count <= 0 or not self.last_printed_char:
            return
        screenful = self.board.width * self.board.height
        if count > screenful:
            count = screenful + count % self.board.width
        self.write_text(self.last_printed_char * count)

    def resize(self, width: int, height: int) -> None:
        """Resize terminal dimensions and the video pages (leaving the status line first)."""
        self.select_active_display(False)
        self.reset_grapheme_state()
        self.board.width = width
        self.board.height = height

        for page in self.videos:
            page.resize(width, height)
        self._fit_page_memory()
        self.current_page = self.alt_page if self.in_alt_screen else self.primary_page
        self.status_page.resize(width, 1)
        # A resize restores the full page, both ways: keeping scroll_top while
        # clamping scroll_bottom can invert the region, and an inverted region
        # stops line feed scrolling at all.
        self.set_scroll_region(0, height - 1)
        self.reset_left_right_margins()

        self.board.cursor.clamp_to_terminal()

    def set_page_columns(self, columns: int) -> None:
        """DECSCPP — change page width without clearing or resetting regions."""
        if columns not in (80, 132) or columns == self.board.width:
            return

        old_width = self.board.width
        old_left = self.left_margin
        old_right = self.right_margin
        full_width_region = old_left == 0 and old_right == old_width - 1

        self.select_active_display(False)
        self.reset_grapheme_state()
        self.board.width = columns
        for page in self.videos:
            page.resize(columns, self.board.height)
        self.status_page.resize(columns, 1)

        if full_width_region:
            self.left_margin = 0
            self.right_margin = columns - 1
        else:
            self.left_margin = min(old_left, columns - 2)
            self.right_margin = max(self.left_margin + 1, min(old_right, columns - 1))
        self.board.cursor.clamp_to_terminal()

    def set_width_policy(self, policy: WidthPolicy) -> None:
        """Use a new policy for future writes on both video pages."""
        self.reset_grapheme_state()
        for page in self.videos:
            page.width_policy = policy

    def clear_screen(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear screen."""
        self.board.cursor.cancel_pending_wrap()
        bg_ansi = self.board.style.background_ansi()

        if mode == constants.ERASE_FROM_CURSOR_TO_END:
            self.current_page.clear_line(
                self.board.cursor.y,
                constants.ERASE_FROM_CURSOR_TO_END,
                self.board.cursor.x,
                bg_ansi,
            )
            for y in range(self.board.cursor.y + 1, self.board.height):
                self.current_page.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            for y in range(self.board.cursor.y):
                self.current_page.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
            self.clear_line(constants.ERASE_FROM_START_TO_CURSOR)
        elif mode == constants.ERASE_ALL:
            for y in range(self.board.height):
                self.current_page.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)

    def clear_line(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear line."""
        self.board.cursor.cancel_pending_wrap()
        bg_ansi = self.board.style.background_ansi()
        self.current_page.clear_line(self.board.cursor.y, mode, self.board.cursor.x, bg_ansi)

    def clear_rect(self, x1: int, y1: int, x2: int, y2: int, ansi_code: str = "") -> None:
        """Clear a rectangular region."""
        self.current_page.clear_region(x1, y1, x2, y2, ansi_code)

    def _selective_clear(self, x: int, y: int) -> None:
        """Clear an intersected glyph only if it is not DECSCA-protected."""
        owner = self.current_page.owner_x(x, y)
        if not self.current_page.get_cell(owner, y)[0].protected:
            self.current_page.set_cell(owner, y, " ", self.board.style.background_ansi())

    def selective_erase_display(self, mode: int) -> None:
        """DECSED — erase in display, leaving DECSCA-protected characters."""
        self.board.cursor.cancel_pending_wrap()
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
        self.board.cursor.cancel_pending_wrap()
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

    def rectangle_styles(self, params) -> set[Style]:
        """The styles in a Pt;Pl;Pb;Pr rectangle of the current page (XTREPORTSGR)."""
        top, left, bottom, right = self._rectangle(*self._four(params))
        page = self.current_page
        return {page.get_cell(x, y)[0] for y in range(top, bottom + 1) for x in range(left, right + 1)}

    @staticmethod
    def _four(params, start=0):
        p = list(params) + [None] * (start + 4)
        return p[start], p[start + 1], p[start + 2], p[start + 3]

    def fill_rectangle(self, params) -> None:
        """DECFRA — fill a rectangle with a character (Pch;Pt;Pl;Pb;Pr).

        Pch is a character code, and DEC restricts it to the printable ranges
        32-126 and 160-255; a value outside them is not a character and the
        whole operation is ignored. Pinning that is what keeps `CSI 999999999$x`
        from reaching chr() and raising ValueError out of the parser feed.
        """
        if params and params[0] and not (32 <= params[0] <= 126 or 160 <= params[0] <= 255):
            return
        char = chr(params[0]) if params and params[0] else " "
        t, left, b, r = self._rectangle(*self._four(params, 1))
        char_width = self.board.width_policy.width(char)
        for y in range(t, b + 1):
            x = left
            while x + char_width - 1 <= r:
                self.current_page.set_cell(x, y, char, self.board.style.current)
                x += char_width
            if x <= r:
                self.current_page.set_cell(x, y, " ", self.board.style.current)

    def erase_rectangle(self, params) -> None:
        """DECERA — erase a rectangle (Pt;Pl;Pb;Pr)."""
        t, left, b, r = self._rectangle(*self._four(params))
        bg = self.board.style.background_ansi()
        for y in range(t, b + 1):
            for x in range(left, r + 1):
                self.current_page.set_cell(x, y, " ", bg)

    def selective_erase_rectangle(self, params) -> None:
        """DECSERA — erase a rectangle, leaving DECSCA-protected characters."""
        t, left, b, r = self._rectangle(*self._four(params))
        for y in range(t, b + 1):
            for x in range(left, r + 1):
                self._selective_clear(x, y)

    def copy_rectangle(self, params) -> None:
        """DECCRA — copy a rectangle to another origin (Pts;Pls;Pbs;Prs;Pps;Ptd;Pld;Ppd), between pages."""
        t, left, b, r = self._rectangle(*self._four(params))
        p = list(params) + [None] * 8
        source, target = self.page_at(p[4]), self.page_at(p[7])
        dt = (p[5] - 1) if p[5] else 0
        dl = (p[6] - 1) if p[6] else 0
        cells = []
        for y in range(t, b + 1):
            row = [source.get_cell(x, y) for x in range(left, r + 1)]
            # A rectangle containing only half of a wide glyph copies blanks
            # at that edge, never an orphaned fragment.
            if row and row[0][1] == "":
                row[0] = (row[0][0], " ")
            if row and r + 1 < self.board.width and source.get_cell(r + 1, y)[1] == "":
                row[-1] = (row[-1][0], " ")
            cells.append(row)
        for dy, row in enumerate(cells):
            ty = dt + dy
            if 0 <= ty < self.board.height and 0 <= dl < self.board.width:
                target.replace_cells(dl, ty, row)

    def set_attr_change_extent(self, ps: int) -> None:
        """DECSACE — 2 = rectangle, else stream (a wrapping run; the power-on default)."""
        self.attr_change_extent = "rectangle" if ps == 2 else "stream"

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
        changed = set()
        for x, y in self._extent_cells(params):
            owner = self.current_page.owner_x(x, y)
            if (owner, y) in changed:
                continue
            changed.add((owner, y))
            cell = self.current_page.get_cell(owner, y)
            self.current_page.set_style(owner, y, cell[0].merge(delta))

    def reverse_attributes_rectangle(self, params) -> None:
        """DECRARA — toggle the given attributes (1/4/5/7) across the area (rectangle or stream)."""
        requested = [p for p in params[4:] if p in _REVERSE_ATTRS] or list(_REVERSE_ATTRS)
        attrs = [_REVERSE_ATTRS[p] for p in requested]
        changed = set()
        for x, y in self._extent_cells(params):
            owner = self.current_page.owner_x(x, y)
            if (owner, y) in changed:
                continue
            changed.add((owner, y))
            cell = self.current_page.get_cell(owner, y)
            style = cell[0]
            for attr in attrs:
                style = style.replace(**{attr: not getattr(style, attr)})
            self.current_page.set_style(owner, y, style)

    def switch_screen(self, alt: bool) -> None:
        """Switch between primary and alternate screen."""
        self.reset_grapheme_state()
        changed = alt != self.in_alt_screen
        if alt and not self.in_alt_screen:
            self.current_page = self.alt_page
            self.in_alt_screen = True
        elif not alt and self.in_alt_screen:
            self.current_page = self.primary_page
            self.in_alt_screen = False
        if changed:
            self.board.modes.reconcile(ModeEffect.MOUSE_CAPTURE)

    def alignment_test(self) -> None:
        """Fill the screen with 'E' characters for alignment testing."""
        test_text = "E" * self.board.width
        for y in range(self.board.height):
            self.current_page.set(0, y, test_text)

    def set_scroll_region(self, top: int, bottom: int) -> None:
        """Set scroll region."""
        self.scroll_top = max(0, min(top, self.board.height - 1))
        self.scroll_bottom = max(self.scroll_top, min(bottom, self.board.height - 1))

    def set_top_and_bottom_margins(self, top: int, bottom: int | None) -> None:
        """DECSTBM — set the scroll region and home the cursor (origin-aware).

        A region of fewer than two lines is ignored, cursor and all (xterm 407).
        """
        bottom = self.board.height - 1 if bottom is None else min(bottom, self.board.height - 1)
        if top >= bottom:
            return
        self.set_scroll_region(top, bottom)
        self.board.cursor.move_to(0, 0)

    def insert_lines(self, count: int) -> None:
        """Insert blank lines at the cursor's row, then return to the left margin (as xterm does)."""
        cursor = self.board.cursor
        cursor.cancel_pending_wrap()
        if count <= 0 or not (
            self.scroll_top <= cursor.y <= self.scroll_bottom and self.left_margin <= cursor.x <= self.right_margin
        ):
            return
        cursor.x = self.left_margin

        if self.left_margin == 0 and self.right_margin == self.board.width - 1 and self.board.style.current.bg is None:
            self.current_page.scroll_region_down(cursor.y, self.scroll_bottom, count)
        else:
            self.current_page.scroll_rectangle_down(
                cursor.y,
                self.scroll_bottom,
                count,
                left=self.left_margin,
                right=self.right_margin,
                style_or_ansi=self.board.style.background_ansi(),
            )

    def delete_lines(self, count: int) -> None:
        """Delete lines at the cursor's row, then return to the left margin (as xterm does)."""
        cursor = self.board.cursor
        cursor.cancel_pending_wrap()
        if count <= 0 or not (
            self.scroll_top <= cursor.y <= self.scroll_bottom and self.left_margin <= cursor.x <= self.right_margin
        ):
            return
        cursor.x = self.left_margin

        if self.left_margin == 0 and self.right_margin == self.board.width - 1 and self.board.style.current.bg is None:
            self.current_page.scroll_region_up(cursor.y, self.scroll_bottom, count)
        else:
            self.current_page.scroll_rectangle_up(
                cursor.y,
                self.scroll_bottom,
                count,
                left=self.left_margin,
                right=self.right_margin,
                style_or_ansi=self.board.style.background_ansi(),
            )

    def insert_characters(self, count: int, ansi_code: str = "") -> None:
        """Insert blank characters at cursor position."""
        cursor = self.board.cursor
        cursor.cancel_pending_wrap()
        if count <= 0 or not (
            self.scroll_top <= cursor.y <= self.scroll_bottom and self.left_margin <= cursor.x <= self.right_margin
        ):
            return
        self._shift_line_segment(cursor.y, cursor.x, self.right_margin, -count, ansi_code)

    def delete_characters(self, count: int) -> None:
        """Delete characters at cursor position."""
        cursor = self.board.cursor
        cursor.cancel_pending_wrap()
        if count <= 0 or not (
            self.scroll_top <= cursor.y <= self.scroll_bottom and self.left_margin <= cursor.x <= self.right_margin
        ):
            return
        self._shift_line_segment(cursor.y, cursor.x, self.right_margin, count)

    def scroll(self, lines: int) -> None:
        """Scroll content within the active scroll region; the status line never scrolls."""
        if lines == 0 or self.scroll_top > self.scroll_bottom or self.status_active:
            return

        abs_lines = abs(lines)
        if self.left_margin == 0 and self.right_margin == self.board.width - 1 and self.board.style.current.bg is None:
            if lines > 0:
                self.current_page.scroll_region_up(self.scroll_top, self.scroll_bottom, abs_lines)
            else:
                self.current_page.scroll_region_down(self.scroll_top, self.scroll_bottom, abs_lines)
        else:
            background = self.board.style.background_ansi()
            if lines > 0:
                self.current_page.scroll_rectangle_up(
                    self.scroll_top,
                    self.scroll_bottom,
                    abs_lines,
                    left=self.left_margin,
                    right=self.right_margin,
                    style_or_ansi=background,
                )
            else:
                self.current_page.scroll_rectangle_down(
                    self.scroll_top,
                    self.scroll_bottom,
                    abs_lines,
                    left=self.left_margin,
                    right=self.right_margin,
                    style_or_ansi=background,
                )

    def _shift_line_segment(self, y: int, x0: int, right: int, columns: int, style_or_ansi=None) -> None:
        """Shift one inclusive row segment; positive is left, negative is right."""
        span = right - x0 + 1
        if columns == 0 or span <= 0:
            return
        n = min(abs(columns), span)
        style = parse_sgr_sequence(style_or_ansi) if isinstance(style_or_ansi, str) else style_or_ansi
        style = Style() if style is None else style
        blank = (style, " ")
        seg = [self.current_page.get_cell(x, y) for x in range(x0, right + 1)]
        cells = seg[n:] + [blank] * n if columns > 0 else [blank] * n + seg[: span - n]
        self.current_page.replace_cells(x0, y, cells, style)

    def _shift_row_segment(
        self,
        x0: int,
        columns: int,
        *,
        top: int | None = None,
        bottom: int | None = None,
        style_or_ansi=None,
    ) -> None:
        """Shift the [x0, right_margin] cells of every scroll-region row by columns.

        columns > 0 pushes content left (blanks appear on the right of the segment);
        columns < 0 pushes it right. Vacated cells take the current background.
        """
        if columns == 0 or self.scroll_top > self.scroll_bottom:
            return
        right = self.right_margin
        if style_or_ansi is None:
            style_or_ansi = self.board.style.background_ansi()
        first = self.scroll_top if top is None else top
        last = self.scroll_bottom if bottom is None else bottom
        for y in range(first, last + 1):
            self._shift_line_segment(y, x0, right, columns, style_or_ansi)

    def pan(self, columns: int, *, full_page: bool = False) -> None:
        """SL/SR — pan the scroll-region rows horizontally within the left/right margins."""
        if full_page:
            self._shift_row_segment(
                self.left_margin,
                columns,
                top=0,
                bottom=self.board.height - 1,
                style_or_ansi=Style(),
            )
        else:
            self._shift_row_segment(self.left_margin, columns)

    def shift_columns(self, count: int) -> None:
        """DECIC (count > 0) / DECDC (count < 0) — insert/delete columns at the cursor.

        Confined to the left/right margin box; a cursor outside it is a no-op.
        """
        x0 = self.board.cursor.display_x  # a pending wrap stays pending, as in xterm
        if not (self.left_margin <= x0 <= self.right_margin):
            return
        # DECIC inserts blanks at x0 (content pushed right = negative shift); DECDC deletes (left).
        self._shift_row_segment(x0, -count)

    def set_left_right_margins(self, left: int | None, right: int | None) -> None:
        """DECSLRM — set the left/right margins (1-based; None/0 = extremes) and home the cursor."""
        width = self.board.width
        left1 = left or 1
        right1 = min(right or width, width)  # clamped to the screen, as in xterm 407
        if not left1 < right1:
            return
        left0 = left1 - 1
        right0 = right1 - 1
        self.left_margin = left0
        self.right_margin = right0
        self.board.cursor.move_to(0, 0)

    def reset_left_right_margins(self) -> None:
        """Restore the margins to the full screen width."""
        self.left_margin = 0
        self.right_margin = self.board.width - 1
        self.board.cursor.cancel_pending_wrap()

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
        """Restore the full scroll region; a hard reset also clears both pages to primary."""
        self.reset_grapheme_state()
        self.set_scroll_region(0, self.board.height - 1)
        self.left_margin, self.right_margin = 0, self.board.width - 1  # a pending wrap survives DECSTR
        if not hard:
            return
        self.set_right_to_left(False)
        self.in_alt_screen = False
        self.page = self.shown_page = 0
        self.current_page = self.primary_page
        self.attr_change_extent = "stream"
        self.status_page.clear_line(0, constants.ERASE_ALL, 0, "")  # RIS erases the status line
        self.select_status_type(self.board.model.status_line_type)
        for buf in self.videos:
            buf.reset_line_attributes()
            buf.reset_wrapped_lines()
            for y in range(self.board.height):
                buf.clear_line(y, constants.ERASE_ALL, 0, "")
        self.last_printed_char = ""

    def set_column_mode(self, columns: int) -> None:
        """DECCOLM — switch 80/132 columns; always clears the screen and homes the cursor."""
        if columns not in (80, 132):
            return
        if self.board.width != columns:
            self.resize(columns, self.board.height)
        self.set_scroll_region(0, self.board.height - 1)
        self.reset_left_right_margins()
        if not self.board.modes.no_clear_column_mode:
            self.clear_screen(constants.ERASE_ALL)
        self.board.cursor.set_position(0, 0)

    def erase_characters(self, count: int) -> None:
        """Erase `count` characters from the cursor with the current style; the cursor stays (ECH)."""
        self.board.cursor.cancel_pending_wrap()
        y = self.board.cursor.y
        style = self.board.style.current
        for x in range(self.board.cursor.x, min(self.board.cursor.x + count, self.board.width)):
            self.current_page.set_cell(x, y, " ", style)
