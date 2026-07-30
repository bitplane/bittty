"""The blitter: writes video memory. Screen and editing operation handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from wcwidth import iter_graphemes

from .. import constants
from ..operations import Operation
from ..style import Style, parse_sgr_sequence
from ..video import Cell, Video
from .base import Device

_REVERSE_ATTRS = {1: "bold", 4: "underline", 5: "blink", 7: "reverse"}
_MAX_CLUSTER_CODEPOINTS = 256
_OVERFLOW_CONTEXT = 32
_ASCII_KEYCAP_BASES = frozenset("#*0123456789")

if TYPE_CHECKING:
    from ..width import WidthPolicy
    from .board import Board


@dataclass(slots=True)
class _ClusterTail:
    page: Video
    row: list
    x: int
    y: int
    text: str
    width: int
    style: Style
    cursor_x: int
    cursor_y: int
    insert_mode: bool
    auto_wrap: bool
    width_policy: WidthPolicy
    board_width: int
    board_height: int
    overflow: bool = False
    context: str = ""
    restore_start: int = 0
    restore_cells: tuple[Cell, ...] = ()
    insert_restore: tuple[Cell, ...] = ()


@dataclass(slots=True)
class _PendingPrefix:
    text: str
    page: Video
    row: list
    cursor_x: int
    cursor_y: int
    insert_mode: bool
    auto_wrap: bool
    width_policy: WidthPolicy
    board_width: int
    board_height: int


class Blitter(Device):
    """Owns the video pages and applies screen/editing operations."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.primary_buffer = Video(board.width, board.height, board.width_policy)
        self.alt_buffer = Video(board.width, board.height, board.width_policy)
        self.current_buffer = self.primary_buffer
        self.in_alt_screen = False
        self.scroll_top = 0
        self.scroll_bottom = board.height - 1
        self.left_margin = 0
        self.right_margin = board.width - 1
        self.attr_change_extent = "rectangle"  # DECSACE: "rectangle" or "stream"
        self.last_printed_char = " "
        self._cluster_tail: _ClusterTail | None = None
        self._pending_prefix: _PendingPrefix | None = None
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
        """Write printable text at the cursor, accounting for terminal columns.

        ASCII runs keep the bulk slice path. Non-ASCII code points are measured
        by the board's width policy and width-2 characters are written
        atomically.
        """
        board = self.board
        code_to_use = ansi_code if ansi_code else board.style.current
        translated_text = board.charset.translate(text)
        cursor = board.cursor
        write = self.current_buffer.insert if board.modes.insert_mode else self.current_buffer.set
        width = board.width

        def write_ascii_run(run: str) -> None:
            remaining = run
            while remaining:
                cursor.prepare_for_text_write()
                space = width - cursor.x
                chunk, remaining = remaining[:space], remaining[space:]
                write(cursor.x, cursor.y, chunk, code_to_use)
                cursor.advance_after_text_write(len(chunk))

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

                cursor.prepare_for_text_write()
                if char_width > width - cursor.x:
                    if board.modes.auto_wrap:
                        cursor.x = width
                        cursor.prepare_for_text_write()
                    else:
                        cursor.x = width - char_width

                write(cursor.x, cursor.y, char, code_to_use)
                cursor.advance_after_text_write(char_width)
                start = index + 1

            if start < len(translated_text):
                write_ascii_run(translated_text[start:])

        if translated_text:
            self.last_printed_char = translated_text[-1]

    def set_grapheme_clustering(self, enabled: bool) -> None:
        """Switch the write callable so disabled mode has no per-run branch."""
        self.reset_grapheme_state()
        if enabled:
            self.write_text = self._write_clustered_entry
        else:
            self.__dict__.pop("write_text", None)

    def _write_clustered_entry(self, text: str, ansi_code: str = "") -> None:
        board = self.board
        code_to_use = ansi_code if ansi_code else board.style.current
        style = code_to_use if isinstance(code_to_use, Style) else parse_sgr_sequence(code_to_use)
        self._write_clustered_text(board.charset.translate(text), style)

    def reset_grapheme_state(self) -> None:
        """Forget streaming state without changing already-written cells."""
        self._cluster_tail = None
        self._pending_prefix = None

    def _tail_is_valid(self, tail: _ClusterTail) -> bool:
        board = self.board
        if (
            self.current_buffer is not tail.page
            or board.width != tail.board_width
            or board.height != tail.board_height
            or board.cursor.x != tail.cursor_x
            or board.cursor.y != tail.cursor_y
            or board.modes.insert_mode != tail.insert_mode
            or board.modes.auto_wrap != tail.auto_wrap
            or board.width_policy != tail.width_policy
            or not (0 <= tail.y < tail.page.height and 0 <= tail.x < tail.page.width)
            or tail.page.grid[tail.y] is not tail.row
        ):
            return False
        head = tail.page.get_cell(tail.x, tail.y)
        if head[0] != tail.style or str(head[1]) != tail.text:
            return False
        if tail.width == 2:
            return tail.x + 1 < tail.page.width and tail.page.get_cell(tail.x + 1, tail.y) == (tail.style, "")
        return type(head[1]) is str

    def _prefix_is_valid(self, prefix: _PendingPrefix) -> bool:
        board = self.board
        return (
            self.current_buffer is prefix.page
            and board.width == prefix.board_width
            and board.height == prefix.board_height
            and board.cursor.x == prefix.cursor_x
            and board.cursor.y == prefix.cursor_y
            and board.modes.insert_mode == prefix.insert_mode
            and board.modes.auto_wrap == prefix.auto_wrap
            and board.width_policy == prefix.width_policy
            and 0 <= prefix.cursor_y < prefix.page.height
            and prefix.page.grid[prefix.cursor_y] is prefix.row
        )

    @staticmethod
    def _is_prepend_cluster(text: str) -> bool:
        """Whether a trailing cluster joins a following ordinary base."""
        iterator = iter_graphemes(text + "A")
        return next(iterator, "") == text + "A"

    def _remember_prefix(self, text: str) -> None:
        board = self.board
        y = board.cursor.y
        self._pending_prefix = _PendingPrefix(
            text=text[-_MAX_CLUSTER_CODEPOINTS:],
            page=self.current_buffer,
            row=self.current_buffer.grid[y],
            cursor_x=board.cursor.x,
            cursor_y=y,
            insert_mode=board.modes.insert_mode,
            auto_wrap=board.modes.auto_wrap,
            width_policy=board.width_policy,
            board_width=board.width,
            board_height=board.height,
        )

    def _snapshot_glyph_target(self, x: int, y: int) -> tuple[int, tuple[Cell, ...], tuple[Cell, ...]]:
        page = self.current_buffer
        row = page.grid[y]
        if self.board.modes.insert_mode:
            return x, (), tuple(row[-2:])

        start = page.owner_x(x, y)
        end = min(page.width, x + 2)
        if end < page.width and row[end][1] == "":
            end += 1
        return start, tuple(row[start:end]), ()

    def _remember_tail(
        self,
        x: int,
        y: int,
        text: str,
        width: int,
        style: Style,
        *,
        overflow=False,
        previous: _ClusterTail | None = None,
        restore_start=0,
        restore_cells=(),
        insert_restore=(),
    ) -> None:
        board = self.board
        if previous is not None:
            restore_start = previous.restore_start
            restore_cells = previous.restore_cells
            insert_restore = previous.insert_restore
        tail = self._cluster_tail
        if tail is None:
            self._cluster_tail = _ClusterTail(
                page=self.current_buffer,
                row=self.current_buffer.grid[y],
                x=x,
                y=y,
                text=text,
                width=width,
                style=style,
                cursor_x=board.cursor.x,
                cursor_y=board.cursor.y,
                insert_mode=board.modes.insert_mode,
                auto_wrap=board.modes.auto_wrap,
                width_policy=board.width_policy,
                board_width=board.width,
                board_height=board.height,
                overflow=overflow,
                context=text[-_OVERFLOW_CONTEXT:],
                restore_start=restore_start,
                restore_cells=restore_cells,
                insert_restore=insert_restore,
            )
            return

        tail.page = self.current_buffer
        tail.row = self.current_buffer.grid[y]
        tail.x = x
        tail.y = y
        tail.text = text
        tail.width = width
        tail.style = style
        tail.cursor_x = board.cursor.x
        tail.cursor_y = board.cursor.y
        tail.insert_mode = board.modes.insert_mode
        tail.auto_wrap = board.modes.auto_wrap
        tail.width_policy = board.width_policy
        tail.board_width = board.width
        tail.board_height = board.height
        tail.overflow = overflow
        tail.context = text[-_OVERFLOW_CONTEXT:]
        tail.restore_start = restore_start
        tail.restore_cells = restore_cells
        tail.insert_restore = insert_restore

    def _write_ascii_cluster_run(self, run: str, style: Style) -> None:
        if not run:
            return
        board = self.board
        cursor = board.cursor
        if board.modes.insert_mode:
            if len(run) > 1:
                remaining = run[:-1]
                while remaining:
                    cursor.prepare_for_text_write()
                    space = board.width - cursor.x
                    chunk, remaining = remaining[:space], remaining[space:]
                    self.current_buffer.insert(cursor.x, cursor.y, chunk, style)
                    cursor.advance_after_text_write(len(chunk))
            self._write_cluster_glyph(run[-1], 1, style)
            return

        remaining = run
        while remaining:
            cursor.prepare_for_text_write()
            space = board.width - cursor.x
            chunk, remaining = remaining[:space], remaining[space:]
            start_x, y = cursor.x, cursor.y
            final_chunk = not remaining
            if final_chunk:
                x = start_x + len(chunk) - 1
                if run[-1] in _ASCII_KEYCAP_BASES:
                    restore_start, restore_cells, _ = self._snapshot_glyph_target(x, y)
                else:
                    restore_start, restore_cells = x, ()
                # If this run's prefix overwrites the head of a wide glyph whose
                # continuation is the candidate cell, record the post-prefix
                # state rather than resurrecting that old glyph on relocation.
                if restore_start < x:
                    adjusted = list(restore_cells)
                    for column in range(restore_start, x):
                        offset = column - start_x
                        if 0 <= offset < len(chunk) - 1:
                            adjusted[column - restore_start] = (style, chunk[offset])
                    adjusted[x - restore_start] = (style, " ")
                    restore_cells = tuple(adjusted)
            self.current_buffer.set(start_x, y, chunk, style)
            cursor.advance_after_text_write(len(chunk))

        self._remember_tail(
            x,
            y,
            run[-1],
            1,
            style,
            restore_start=restore_start,
            restore_cells=restore_cells,
        )
        self.last_printed_char = run[-1]

    def _write_cluster_glyph(self, text: str, width: int, style: Style) -> None:
        board = self.board
        if width == 0 or width > board.width:
            return
        cursor = board.cursor
        cursor.prepare_for_text_write()
        if width > board.width - cursor.x:
            if board.modes.auto_wrap:
                cursor.x = board.width
                cursor.prepare_for_text_write()
            else:
                cursor.x = board.width - width
        x, y = cursor.x, cursor.y
        restore_start, restore_cells, insert_restore = self._snapshot_glyph_target(x, y)
        self.current_buffer.write_glyph(
            x,
            y,
            text,
            width,
            style,
            insert=board.modes.insert_mode,
        )
        cursor.advance_after_text_write(width)
        self._remember_tail(
            x,
            y,
            text,
            width,
            style,
            restore_start=restore_start,
            restore_cells=restore_cells,
            insert_restore=insert_restore,
        )
        self.last_printed_char = text

    def _extend_tail(self, tail: _ClusterTail, complete_text: str) -> None:
        display_text = complete_text[:_MAX_CLUSTER_CODEPOINTS]
        overflow = len(complete_text) > _MAX_CLUSTER_CODEPOINTS
        if tail.overflow:
            display_text = tail.text
            overflow = True

        new_width = tail.width_policy.grapheme_width(display_text)
        if new_width == 0:
            return
        board = self.board
        page = tail.page

        if tail.x + new_width <= board.width:
            page.resize_glyph(
                tail.x,
                tail.y,
                display_text,
                tail.width,
                new_width,
                tail.style,
                insert=tail.insert_mode,
                restore_start=tail.restore_start,
                restore_cells=tail.restore_cells,
                insert_restore=tail.insert_restore,
            )
            if tail.auto_wrap:
                board.cursor.x = tail.x + new_width
            else:
                board.cursor.x = min(board.width - 1, tail.x + new_width)
            board.cursor.y = tail.y
            self._remember_tail(
                tail.x,
                tail.y,
                display_text,
                new_width,
                tail.style,
                overflow=overflow,
                previous=tail,
            )
        else:
            page.remove_glyph(
                tail.x,
                tail.y,
                tail.width,
                tail.style,
                inserted=tail.insert_mode,
                restore_start=tail.restore_start,
                restore_cells=tail.restore_cells,
                insert_restore=tail.insert_restore,
            )
            if tail.auto_wrap:
                board.cursor.x = board.width
                board.cursor.y = tail.y
            else:
                board.cursor.x = board.width - new_width
                board.cursor.y = tail.y
            self._write_cluster_glyph(display_text, new_width, tail.style)
            if self._cluster_tail is not None:
                self._cluster_tail.overflow = overflow
                self._cluster_tail.context = complete_text[-_OVERFLOW_CONTEXT:]
        if self._cluster_tail is not None:
            self._cluster_tail.context = complete_text[-_OVERFLOW_CONTEXT:]
        self.last_printed_char = display_text

    def _attach_to_tail(self, text: str) -> str:
        tail = self._cluster_tail
        if tail is None or not self._tail_is_valid(tail):
            self._cluster_tail = None
            return text

        base = tail.context if tail.overflow else tail.text
        iterator = iter_graphemes(base + text)
        first = next(iterator, "")
        if not first.startswith(base) or len(first) == len(base):
            return text

        consumed = len(first) - len(base)
        if tail.overflow:
            complete = tail.text
        else:
            complete = first
        self._extend_tail(tail, complete)
        if self._cluster_tail is not None and tail.overflow:
            self._cluster_tail.context = first[-_OVERFLOW_CONTEXT:]
        return text[consumed:]

    def _write_new_clusters(self, text: str, style: Style) -> None:
        iterator = iter_graphemes(text)
        pending = next(iterator, None)
        if pending is None:
            return

        ascii_parts: list[str] = []

        def flush_ascii() -> None:
            if ascii_parts:
                self._write_ascii_cluster_run("".join(ascii_parts), style)
                ascii_parts.clear()

        for cluster in iterator:
            if pending.isascii() and len(pending) == 1:
                ascii_parts.append(pending)
            else:
                flush_ascii()
                width = self.board.width_policy.grapheme_width(pending)
                if width:
                    display = pending[:_MAX_CLUSTER_CODEPOINTS]
                    self._write_cluster_glyph(display, self.board.width_policy.grapheme_width(display), style)
                    if self._cluster_tail is not None and len(pending) > _MAX_CLUSTER_CODEPOINTS:
                        self._cluster_tail.overflow = True
                        self._cluster_tail.context = pending[-_OVERFLOW_CONTEXT:]
            pending = cluster

        if self._is_prepend_cluster(pending):
            flush_ascii()
            self._remember_prefix(pending)
        elif pending.isascii() and len(pending) == 1:
            ascii_parts.append(pending)
            flush_ascii()
        else:
            flush_ascii()
            width = self.board.width_policy.grapheme_width(pending)
            if width:
                display = pending[:_MAX_CLUSTER_CODEPOINTS]
                self._write_cluster_glyph(display, self.board.width_policy.grapheme_width(display), style)
                if self._cluster_tail is not None and len(pending) > _MAX_CLUSTER_CODEPOINTS:
                    self._cluster_tail.overflow = True
                    self._cluster_tail.context = pending[-_OVERFLOW_CONTEXT:]

    def _write_clustered_text(self, text: str, style: Style) -> None:
        if not text:
            return

        prefix = self._pending_prefix
        if prefix is None and text.isascii():
            # ASCII always starts a new cluster (the only forward-joining case,
            # Prepend, is held separately), so avoid invoking the segmenter.
            self._write_ascii_cluster_run(text, style)
            return

        if prefix is not None:
            self._pending_prefix = None
            if self._prefix_is_valid(prefix):
                text = prefix.text + text
            else:
                prefix = None

        if prefix is None:
            text = self._attach_to_tail(text)
            if not text:
                return

        if text.isascii():
            self._write_ascii_cluster_run(text, style)
        else:
            self._write_new_clusters(text, style)

    def repeat_last_character(self, count: int) -> None:
        """Repeat the last printed character count times."""
        if count > 0 and self.last_printed_char:
            self.write_text(self.last_printed_char * count)

    def resize(self, width: int, height: int) -> None:
        """Resize terminal dimensions and screen buffers."""
        self.reset_grapheme_state()
        self.board.width = width
        self.board.height = height

        self.primary_buffer.resize(width, height)
        self.alt_buffer.resize(width, height)
        self.scroll_bottom = height - 1
        self.reset_left_right_margins()

        self.board.cursor.clamp_to_terminal()

    def set_width_policy(self, policy: WidthPolicy) -> None:
        """Use a new policy for future writes on both video pages."""
        self.reset_grapheme_state()
        self.primary_buffer.width_policy = policy
        self.alt_buffer.width_policy = policy

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

    def clear_line(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear line."""
        bg_ansi = self.board.style.background_ansi()
        self.current_buffer.clear_line(self.board.cursor.y, mode, self.board.cursor.x, bg_ansi)

    def clear_rect(self, x1: int, y1: int, x2: int, y2: int, ansi_code: str = "") -> None:
        """Clear a rectangular region."""
        self.current_buffer.clear_region(x1, y1, x2, y2, ansi_code)

    def _selective_clear(self, x: int, y: int) -> None:
        """Clear an intersected glyph only if it is not DECSCA-protected."""
        owner = self.current_buffer.owner_x(x, y)
        if not self.current_buffer.get_cell(owner, y)[0].protected:
            self.current_buffer.set_cell(owner, y, " ", self.board.style.background_ansi())

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
        char_width = self.board.width_policy.width(char)
        for y in range(t, b + 1):
            x = left
            while x + char_width - 1 <= r:
                self.current_buffer.set_cell(x, y, char, self.board.style.current)
                x += char_width
            if x <= r:
                self.current_buffer.set_cell(x, y, " ", self.board.style.current)

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
        cells = []
        for y in range(t, b + 1):
            row = [self.current_buffer.get_cell(x, y) for x in range(left, r + 1)]
            # A rectangle containing only half of a wide glyph copies blanks
            # at that edge, never an orphaned fragment.
            if row and row[0][1] == "":
                row[0] = (row[0][0], " ")
            if row and r + 1 < self.board.width and self.current_buffer.get_cell(r + 1, y)[1] == "":
                row[-1] = (row[-1][0], " ")
            cells.append(row)
        for dy, row in enumerate(cells):
            ty = dt + dy
            if 0 <= ty < self.board.height and 0 <= dl < self.board.width:
                self.current_buffer.replace_cells(dl, ty, row)

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
        changed = set()
        for x, y in self._extent_cells(params):
            owner = self.current_buffer.owner_x(x, y)
            if (owner, y) in changed:
                continue
            changed.add((owner, y))
            cell = self.current_buffer.get_cell(owner, y)
            self.current_buffer.set_style(owner, y, cell[0].merge(delta))

    def reverse_attributes_rectangle(self, params) -> None:
        """DECRARA — toggle the given attributes (1/4/5/7) across the area (rectangle or stream)."""
        requested = [p for p in params[4:] if p in _REVERSE_ATTRS] or list(_REVERSE_ATTRS)
        attrs = [_REVERSE_ATTRS[p] for p in requested]
        changed = set()
        for x, y in self._extent_cells(params):
            owner = self.current_buffer.owner_x(x, y)
            if (owner, y) in changed:
                continue
            changed.add((owner, y))
            cell = self.current_buffer.get_cell(owner, y)
            style = cell[0]
            for attr in attrs:
                style = style.replace(**{attr: not getattr(style, attr)})
            self.current_buffer.set_style(owner, y, style)

    def switch_screen(self, alt: bool) -> None:
        """Switch between primary and alternate screen."""
        self.reset_grapheme_state()
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
        cursor = self.board.cursor
        if count <= 0 or not (
            self.scroll_top <= cursor.y <= self.scroll_bottom and self.left_margin <= cursor.x <= self.right_margin
        ):
            return

        if self.left_margin == 0 and self.right_margin == self.board.width - 1 and self.board.style.current.bg is None:
            self.current_buffer.scroll_region_down(cursor.y, self.scroll_bottom, count)
        else:
            self.current_buffer.scroll_rectangle_down(
                cursor.y,
                self.scroll_bottom,
                count,
                left=self.left_margin,
                right=self.right_margin,
                style_or_ansi=self.board.style.background_ansi(),
            )

    def delete_lines(self, count: int) -> None:
        """Delete lines at cursor position."""
        cursor = self.board.cursor
        if count <= 0 or not (
            self.scroll_top <= cursor.y <= self.scroll_bottom and self.left_margin <= cursor.x <= self.right_margin
        ):
            return

        if self.left_margin == 0 and self.right_margin == self.board.width - 1 and self.board.style.current.bg is None:
            self.current_buffer.scroll_region_up(cursor.y, self.scroll_bottom, count)
        else:
            self.current_buffer.scroll_rectangle_up(
                cursor.y,
                self.scroll_bottom,
                count,
                left=self.left_margin,
                right=self.right_margin,
                style_or_ansi=self.board.style.background_ansi(),
            )

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
        if self.left_margin == 0 and self.right_margin == self.board.width - 1 and self.board.style.current.bg is None:
            if lines > 0:
                self.current_buffer.scroll_region_up(self.scroll_top, self.scroll_bottom, abs_lines)
            else:
                self.current_buffer.scroll_region_down(self.scroll_top, self.scroll_bottom, abs_lines)
        else:
            background = self.board.style.background_ansi()
            if lines > 0:
                self.current_buffer.scroll_rectangle_up(
                    self.scroll_top,
                    self.scroll_bottom,
                    abs_lines,
                    left=self.left_margin,
                    right=self.right_margin,
                    style_or_ansi=background,
                )
            else:
                self.current_buffer.scroll_rectangle_down(
                    self.scroll_top,
                    self.scroll_bottom,
                    abs_lines,
                    left=self.left_margin,
                    right=self.right_margin,
                    style_or_ansi=background,
                )

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
            style = parse_sgr_sequence(bg) if bg else Style()
            cells = [(style, " ") if cell is None else cell for cell in seg]
            self.current_buffer.replace_cells(x0, y, cells, bg)

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
        self.reset_grapheme_state()
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
        """DECCOLM — switch 80/132 columns; always clears the screen and homes the cursor."""
        if columns not in (80, 132):
            return
        if self.board.width != columns:
            self.resize(columns, self.board.height)
        self.set_scroll_region(0, self.board.height - 1)
        self.reset_left_right_margins()
        self.clear_screen(constants.ERASE_ALL)
        self.board.cursor.set_position(0, 0)

    def erase_characters(self, count: int) -> None:
        """Erase `count` characters from the cursor with the current style; the cursor stays (ECH)."""
        y = self.board.cursor.y
        style = self.board.style.current
        for x in range(self.board.cursor.x, min(self.board.cursor.x + count, self.board.width)):
            self.current_buffer.set_cell(x, y, " ", style)
