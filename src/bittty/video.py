"""Video memory: the 2D cell grid the blitter writes and terminals render.

A Board has two pages of it (primary and alternate).
"""

from __future__ import annotations

from . import constants
from .style import RESET_CODE, Style, parse_sgr_sequence
from .width import DEFAULT_WIDTH_POLICY, WidthPolicy


# Type alias for a cell: (Style, character). An empty character is the
# continuation column of a width-2 character stored in the preceding cell.
Cell = tuple[Style, str]
CONTINUATION = ""


class WideHead(str):
    """A string stored as the head of a width-2 glyph."""


def _coerce_style(style_or_ansi) -> Style:
    """Normalise a Style | ANSI-string | None argument to a Style."""
    if isinstance(style_or_ansi, Style):
        return style_or_ansi
    if isinstance(style_or_ansi, str) and style_or_ansi:
        return parse_sgr_sequence(style_or_ansi)
    return Style()


class Video:
    """A 2D grid that stores terminal content."""

    def __init__(self, width: int, height: int, width_policy: WidthPolicy | None = None) -> None:
        """Initialize buffer with given dimensions."""
        self.width = width
        self.height = height
        self.width_policy = width_policy or DEFAULT_WIDTH_POLICY

        # Cache a default empty style + cell to avoid rebuilding them (cells are
        # immutable tuples, always replaced never mutated, so one instance is safe to share).
        self._empty_style = Style()
        self._empty_cell: Cell = (self._empty_style, " ")

        # Initialize grid with empty cells (default style, space character)
        self.grid: list[list[Cell]] = []
        for _ in range(height):
            self.grid.append(self._create_empty_row())

        # Per-line DECDHL/DECDWL/DECSWL attribute, kept parallel to grid rows.
        self.line_attributes: list[str] = [constants.LINE_SINGLE] * height

        # Dirty tracking: readers own the clock. Writes stamp the CURRENT
        # epoch (one store — no increment on the hot path); a renderer calls
        # observe() to open a new epoch after it snapshots. Targeted writes
        # stamp their row in row_gen; whole-page upheavals (full scroll,
        # resize) stamp page_gen instead of touching every row.
        self.generation = 1
        self.page_gen = 0
        self.row_gen: list[int] = [0] * height

    def _touch_row(self, y: int) -> None:
        """Stamp a row as changed in the current epoch."""
        self.row_gen[y] = self.generation

    def _touch_page(self) -> None:
        """Stamp the whole page as changed in the current epoch."""
        self.page_gen = self.generation

    def _touch_scrolled(self, top: int, bottom: int) -> None:
        """Stamp a scrolled region: whole page for a full-height scroll (the hot
        path — one store instead of a stamp per row), per-row otherwise."""
        if top == 0 and bottom == self.height - 1:
            self.page_gen = self.generation
            return
        g = self.generation
        for y in range(top, bottom + 1):
            self.row_gen[y] = g

    def observe(self) -> int:
        """Snapshot for dirty tracking: close the current epoch, open a new one.

        Returns the new epoch; rows stamped at or after it are dirty relative
        to this observation. Each reader keeps its own returned value.
        """
        self.generation += 1
        return self.generation

    def dirty_rows(self, seen: int) -> list[int]:
        """Rows changed since `seen` (a value returned by observe())."""
        if self.page_gen >= seen:
            return list(range(self.height))
        return [y for y, g in enumerate(self.row_gen) if g >= seen]

    def _create_empty_row(self, width: int | None = None) -> list[Cell]:
        """Create a row filled with the shared empty cell (list-multiply, no per-cell build)."""
        return [self._empty_cell] * (self.width if width is None else width)

    def _text_cells(self, text: str, style: Style, available: int | None = None) -> list[Cell]:
        """Encode code points as cells without splitting a width-2 character."""
        if text.isascii():
            if available is not None:
                text = text[:available]
            return [(style, char) for char in text]

        cells: list[Cell] = []
        for char in text:
            char_width = self.width_policy.width(char)
            if available is not None and len(cells) + char_width > available:
                break
            if char_width == 2:
                cells.append((style, WideHead(char)))
                cells.append((style, CONTINUATION))
            else:
                cells.append((style, char))
        return cells

    @staticmethod
    def _owner_in_row(row: list[Cell], x: int) -> int:
        """Return the head column owning x."""
        if 0 < x < len(row) and row[x][1] == CONTINUATION and isinstance(row[x - 1][1], WideHead):
            return x - 1
        return x

    def owner_x(self, x: int, y: int) -> int:
        """Return the head column of the glyph occupying (x, y)."""
        if not (0 <= y < self.height and 0 <= x < self.width):
            return x
        return self._owner_in_row(self.grid[y], x)

    def _clear_glyph(self, row: list[Cell], x: int, style: Style) -> None:
        """Blank the complete glyph intersecting x."""
        if not (0 <= x < len(row)):
            return
        owner = self._owner_in_row(row, x)
        row[owner] = (style, " ")
        if owner + 1 < len(row) and row[owner + 1][1] == CONTINUATION:
            row[owner + 1] = (style, " ")

    def _erase_range(self, row: list[Cell], left: int, right: int, style: Style) -> None:
        """Blank [left, right), expanding across intersected wide glyphs."""
        if right <= left:
            return
        left = max(0, left)
        right = min(len(row), right)
        if left < len(row) and row[left][1] == CONTINUATION:
            left -= 1
        if right < len(row) and row[right][1] == CONTINUATION:
            right += 1
        row[left:right] = [(style, " ")] * (right - left)

    def _prepare_overwrite(self, row: list[Cell], left: int, right: int, style: Style) -> None:
        """Clear old glyphs split by overwriting [left, right)."""
        if not row or right <= left:
            return
        if 0 <= left < len(row) and row[left][1] == CONTINUATION:
            self._clear_glyph(row, left, style)
        if 0 < right < len(row) and row[right][1] == CONTINUATION:
            self._clear_glyph(row, right, style)

    def normalize_row(self, y: int, style_or_ansi=None) -> None:
        """Repair orphaned heads/continuations after a bulk cell movement."""
        if not (0 <= y < self.height):
            return
        row = self.grid[y]
        style = _coerce_style(style_or_ansi)
        x = 0
        while x < len(row):
            char = row[x][1]
            if isinstance(char, WideHead):
                if x + 1 >= len(row) or row[x + 1][1] != CONTINUATION:
                    row[x] = (style, " ")
                    x += 1
                    continue
                # A continuation always carries its head's style.
                row[x + 1] = (row[x][0], CONTINUATION)
                x += 2
                continue
            if char == CONTINUATION:
                row[x] = (style, " ")
            x += 1

    def replace_cells(self, x: int, y: int, cells: list[Cell], style_or_ansi=None) -> None:
        """Paste raw cells at x, erase split destination glyphs, then normalize."""
        if not (0 <= y < self.height and 0 <= x < self.width) or not cells:
            return
        right = min(x + len(cells), self.width)
        style = _coerce_style(style_or_ansi)
        row = self.grid[y]
        self._prepare_overwrite(row, x, right, style)
        row[x:right] = cells[: right - x]
        self.normalize_row(y, style)
        self._touch_row(y)

    def set_style(self, x: int, y: int, style: Style) -> None:
        """Apply a style atomically to the glyph occupying one cell."""
        if not (0 <= y < self.height and 0 <= x < self.width):
            return
        row = self.grid[y]
        owner = self._owner_in_row(row, x)
        char = row[owner][1]
        row[owner] = (style, char)
        if owner + 1 < self.width and row[owner + 1][1] == CONTINUATION:
            row[owner + 1] = (style, CONTINUATION)
        self._touch_row(y)

    def set_line_attribute(self, y: int, attribute: str) -> None:
        """Set a line's DECDHL/DECDWL/DECSWL attribute."""
        if 0 <= y < self.height:
            self.line_attributes[y] = attribute
            self._touch_row(y)

    def get_line_attribute(self, y: int) -> str:
        """Return a line's width/height attribute (single by default)."""
        if 0 <= y < self.height:
            return self.line_attributes[y]
        return constants.LINE_SINGLE

    def reset_line_attributes(self) -> None:
        """Return every line to single-width, single-height (RIS)."""
        self.line_attributes = [constants.LINE_SINGLE] * self.height
        self._touch_page()

    def get_content(self) -> list[list[Cell]]:
        """Get buffer content as a 2D grid."""
        return [row[:] for row in self.grid]

    def get_cell(self, x: int, y: int) -> Cell:
        """Get cell at position."""
        if 0 <= y < self.height and 0 <= x < self.width:
            return self.grid[y][x]
        return (Style(), " ")

    def set_cell(self, x: int, y: int, char: str, style_or_ansi=None) -> None:
        """Set a single cell at position.

        Args:
            x, y: Position
            char: Character to store
            style_or_ansi: Either a Style object or ANSI string (for backward compatibility)
        """
        if not (0 <= y < self.height and 0 <= x < self.width) or not char:
            return
        self.set(x, y, char[0], style_or_ansi)

    def set(self, x: int, y: int, text: str, style_or_ansi=None) -> None:
        """Set text at position, overwriting existing content."""
        if not (0 <= y < self.height):
            return

        if x < 0 or x >= self.width or not text:
            return
        style = _coerce_style(style_or_ansi)
        cells = self._text_cells(text, style, self.width - x)
        if not cells:
            # A wide character cannot be represented in the final column.
            self._erase_range(self.grid[y], x, x + 1, style)
            self._touch_row(y)
            return

        end = x + len(cells)
        row = self.grid[y]
        self._prepare_overwrite(row, x, end, style)
        self.row_gen[y] = self.generation
        if len(cells) == 1:  # single cell (the common case for TUI repaints)
            row[x] = cells[0]
            return
        row[x:end] = cells

    def write_glyph(
        self,
        x: int,
        y: int,
        text: str,
        cell_width: int,
        style_or_ansi=None,
        *,
        insert: bool = False,
    ) -> None:
        """Write one already-segmented glyph as an atomic one/two-cell unit."""
        if not (0 <= y < self.height and 0 <= x < self.width) or not text or cell_width not in (1, 2):
            return
        if x + cell_width > self.width:
            return

        style = _coerce_style(style_or_ansi)
        cells: list[Cell]
        if cell_width == 2:
            cells = [(style, WideHead(text)), (style, CONTINUATION)]
        else:
            cells = [(style, text)]

        row = self.grid[y]
        if insert:
            if row[x][1] == CONTINUATION:
                self._clear_glyph(row, x, style)
            self.grid[y] = (row[:x] + cells + row[x:])[: self.width]
            self.normalize_row(y, style)
        else:
            right = x + cell_width
            self._prepare_overwrite(row, x, right, style)
            row[x:right] = cells
        self._touch_row(y)

    def resize_glyph(
        self,
        x: int,
        y: int,
        text: str,
        old_width: int,
        new_width: int,
        style: Style,
        *,
        insert: bool = False,
        restore_start: int = 0,
        restore_cells: tuple[Cell, ...] = (),
        insert_restore: tuple[Cell, ...] = (),
    ) -> None:
        """Replace the last glyph and adjust its occupied columns atomically."""
        if (
            not (0 <= y < self.height and 0 <= x < self.width)
            or not text
            or old_width not in (1, 2)
            or new_width not in (1, 2)
            or x + old_width > self.width
            or x + new_width > self.width
        ):
            return

        row = self.grid[y]
        if old_width == new_width:
            row[x] = (style, WideHead(text) if new_width == 2 else text)
            if new_width == 2:
                row[x + 1] = (style, CONTINUATION)
            self._touch_row(y)
            return

        if insert:
            del row[x : x + old_width]
            row.extend(insert_restore[-old_width:])
            row.extend([self._empty_cell] * (self.width - len(row)))
            del row[self.width :]
            self.normalize_row(y, style)
        elif restore_cells:
            row[restore_start : restore_start + len(restore_cells)] = restore_cells
            self.normalize_row(y, style)
        else:
            self._erase_range(row, x, x + old_width, style)
        self.write_glyph(x, y, text, new_width, style, insert=insert)

    def remove_glyph(
        self,
        x: int,
        y: int,
        cell_width: int,
        style: Style,
        *,
        inserted: bool = False,
        restore_start: int = 0,
        restore_cells: tuple[Cell, ...] = (),
        insert_restore: tuple[Cell, ...] = (),
    ) -> None:
        """Remove a speculative glyph before relocating a changed-width cluster."""
        if not (0 <= y < self.height and 0 <= x < self.width) or cell_width not in (1, 2):
            return
        row = self.grid[y]
        if inserted:
            del row[x : min(x + cell_width, self.width)]
            restored = list(insert_restore[-cell_width:])
            row.extend(restored)
            row.extend([self._empty_cell] * (self.width - len(row)))
            del row[self.width :]
            self.normalize_row(y, style)
        elif restore_cells:
            row[restore_start : restore_start + len(restore_cells)] = restore_cells
        else:
            self._erase_range(row, x, x + cell_width, style)
        self._touch_row(y)

    def insert(self, x: int, y: int, text: str, style_or_ansi=None) -> None:
        """Insert text at position, shifting existing content right."""
        if not (0 <= y < self.height) or x >= self.width:
            return

        if x < 0 or not text:
            return
        style = _coerce_style(style_or_ansi)
        row = self.grid[y]
        new_cells = self._text_cells(text, style, self.width - x)
        if not new_cells:
            return
        if row[x][1] == CONTINUATION:
            self._clear_glyph(row, x, style)
        self.grid[y] = (row[:x] + new_cells + row[x:])[: self.width]
        self.normalize_row(y, style)
        self._touch_row(y)

    def delete(self, x: int, y: int, count: int = 1) -> None:
        """Delete characters at position."""
        if not (0 <= y < self.height) or x >= self.width:
            return

        if count <= 0:
            return
        row = self.grid[y]
        end_pos = min(x + count, len(row))
        style = self._empty_style
        if row[x][1] == CONTINUATION:
            self._clear_glyph(row, x, style)
        if end_pos < len(row) and row[end_pos][1] == CONTINUATION:
            self._clear_glyph(row, end_pos, style)
        new_row = row[:x] + row[end_pos:]
        new_row.extend([self._empty_cell] * (self.width - len(new_row)))
        self.grid[y] = new_row
        self.normalize_row(y)
        self._touch_row(y)

    def clear_region(self, x1: int, y1: int, x2: int, y2: int, style_or_ansi=None) -> None:
        """Clear a rectangular region."""
        style = _coerce_style(style_or_ansi)

        left, right = max(0, x1), min(self.width, x2 + 1)
        if right <= left:
            return
        g = self.generation
        for y in range(max(0, y1), min(self.height, y2 + 1)):
            self._erase_range(self.grid[y], left, right, style)
            self.row_gen[y] = g

    def clear_line(
        self, y: int, mode: int = constants.ERASE_FROM_CURSOR_TO_END, cursor_x: int = 0, style_or_ansi=None
    ) -> None:
        """Clear line content."""
        if not (0 <= y < self.height):
            return

        style = _coerce_style(style_or_ansi)

        self._touch_row(y)
        if mode == constants.ERASE_FROM_CURSOR_TO_END:
            if cursor_x < self.width:
                self._erase_range(self.grid[y], cursor_x, self.width, style)
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            n = min(cursor_x + 1, self.width)
            self._erase_range(self.grid[y], 0, n, style)
        elif mode == constants.ERASE_ALL:
            # Clear entire line - use cached style if it's the default empty style
            if style is self._empty_style:
                self.grid[y] = self._create_empty_row()
            else:
                self.grid[y] = [(style, " ") for _ in range(self.width)]

    def scroll_up(self, count: int) -> None:
        """Scroll content up, removing top lines and adding blank lines at bottom."""
        count = min(count, len(self.grid))  # Clamp to available rows
        if count <= 0:
            return

        # Bulk remove from top and bulk add to bottom
        del self.grid[:count]
        # Pre-create empty rows in bulk
        empty_rows = [self._create_empty_row() for _ in range(count)]
        self.grid.extend(empty_rows)

        del self.line_attributes[:count]
        self.line_attributes.extend([constants.LINE_SINGLE] * count)
        self._touch_page()

    def scroll_down(self, count: int) -> None:
        """Scroll content down, removing bottom lines and adding blank lines at top."""
        count = min(count, len(self.grid))  # Clamp to available rows
        if count <= 0:
            return

        # Bulk remove from bottom and bulk add to top
        del self.grid[-count:]
        # Pre-create empty rows in bulk and insert at top
        empty_rows = [self._create_empty_row() for _ in range(count)]
        self.grid[:0] = empty_rows

        del self.line_attributes[-count:]
        self.line_attributes[:0] = [constants.LINE_SINGLE] * count
        self._touch_page()

    def scroll_region_up(
        self,
        top: int,
        bottom: int,
        count: int,
    ) -> None:
        """Scroll complete rows within a vertical region using bulk slices."""
        if count <= 0 or top > bottom or bottom >= self.height:
            return

        count = min(count, bottom - top + 1)
        self.grid[top : bottom + 1 - count] = self.grid[top + count : bottom + 1]
        self.line_attributes[top : bottom + 1 - count] = self.line_attributes[top + count : bottom + 1]
        for y in range(bottom + 1 - count, bottom + 1):
            self.grid[y] = self._create_empty_row()
            self.line_attributes[y] = constants.LINE_SINGLE
        self._touch_scrolled(top, bottom)

    def scroll_rectangle_up(
        self,
        top: int,
        bottom: int,
        count: int,
        *,
        left: int = 0,
        right: int | None = None,
        style_or_ansi=None,
    ) -> None:
        """Scroll an inclusive rectangular region up by ``count`` rows.

        Full-width regions retain the bulk row-slice path used by ordinary
        terminal scrolling. Partial-width regions copy only their cell slices,
        leaving neighbouring panes untouched.
        """
        if left == 0 and right is None and style_or_ansi is None:
            self.scroll_region_up(top, bottom, count)
            return

        right = self.width - 1 if right is None else right
        if (
            count <= 0
            or top < 0
            or top > bottom
            or bottom >= self.height
            or left < 0
            or left > right
            or right >= self.width
        ):
            return

        region_height = bottom - top + 1
        count = min(count, region_height)
        style = self._empty_style if style_or_ansi is None or style_or_ansi == "" else _coerce_style(style_or_ansi)
        blank = self._empty_cell if style == self._empty_style else (style, " ")

        if left == 0 and right == self.width - 1:
            # The common path: move complete row objects and their attributes.
            self.grid[top : bottom + 1 - count] = self.grid[top + count : bottom + 1]
            self.line_attributes[top : bottom + 1 - count] = self.line_attributes[top + count : bottom + 1]

            for y in range(bottom + 1 - count, bottom + 1):
                self.grid[y] = [blank] * self.width
                self.line_attributes[y] = constants.LINE_SINGLE
        else:
            end = right + 1
            for y in range(top, bottom + 1 - count):
                cells = self.grid[y + count][left:end]
                # Never move only half of a wide glyph across a rectangle edge.
                if cells[0][1] == CONTINUATION:
                    cells[0] = blank
                if isinstance(cells[-1][1], WideHead):
                    cells[-1] = blank
                row = self.grid[y]
                self._prepare_overwrite(row, left, end, style)
                row[left:end] = cells

            for y in range(bottom + 1 - count, bottom + 1):
                self._erase_range(self.grid[y], left, end, style)

            # A partial-row operation cannot move a row-wide DECDWL/DECDHL
            # attribute without also changing cells outside the rectangle.

        self._touch_scrolled(top, bottom)

    def scroll_region_down(
        self,
        top: int,
        bottom: int,
        count: int,
    ) -> None:
        """Scroll complete rows within a vertical region using bulk slices."""
        if count <= 0 or top > bottom or bottom >= self.height:
            return

        count = min(count, bottom - top + 1)
        self.grid[top + count : bottom + 1] = self.grid[top : bottom + 1 - count]
        self.line_attributes[top + count : bottom + 1] = self.line_attributes[top : bottom + 1 - count]
        for y in range(top, top + count):
            self.grid[y] = self._create_empty_row()
            self.line_attributes[y] = constants.LINE_SINGLE
        self._touch_scrolled(top, bottom)

    def scroll_rectangle_down(
        self,
        top: int,
        bottom: int,
        count: int,
        *,
        left: int = 0,
        right: int | None = None,
        style_or_ansi=None,
    ) -> None:
        """Scroll an inclusive rectangular region down by ``count`` rows."""
        if left == 0 and right is None and style_or_ansi is None:
            self.scroll_region_down(top, bottom, count)
            return

        right = self.width - 1 if right is None else right
        if (
            count <= 0
            or top < 0
            or top > bottom
            or bottom >= self.height
            or left < 0
            or left > right
            or right >= self.width
        ):
            return

        region_height = bottom - top + 1
        count = min(count, region_height)
        style = self._empty_style if style_or_ansi is None or style_or_ansi == "" else _coerce_style(style_or_ansi)
        blank = self._empty_cell if style == self._empty_style else (style, " ")

        if left == 0 and right == self.width - 1:
            self.grid[top + count : bottom + 1] = self.grid[top : bottom + 1 - count]
            self.line_attributes[top + count : bottom + 1] = self.line_attributes[top : bottom + 1 - count]

            for y in range(top, top + count):
                self.grid[y] = [blank] * self.width
                self.line_attributes[y] = constants.LINE_SINGLE
        else:
            end = right + 1
            for y in range(bottom, top + count - 1, -1):
                cells = self.grid[y - count][left:end]
                if cells[0][1] == CONTINUATION:
                    cells[0] = blank
                if isinstance(cells[-1][1], WideHead):
                    cells[-1] = blank
                row = self.grid[y]
                self._prepare_overwrite(row, left, end, style)
                row[left:end] = cells

            for y in range(top, top + count):
                self._erase_range(self.grid[y], left, end, style)

        self._touch_scrolled(top, bottom)

    def resize(self, width: int, height: int) -> None:
        """Resize buffer to new dimensions."""
        # Adjust number of rows
        if len(self.grid) < height:
            # Add new rows
            for _ in range(height - len(self.grid)):
                self.grid.append(self._create_empty_row(width))
            self.line_attributes.extend([constants.LINE_SINGLE] * (height - len(self.line_attributes)))
        elif len(self.grid) > height:
            # Remove excess rows
            self.grid = self.grid[:height]
            self.line_attributes = self.line_attributes[:height]

        # Adjust width of each row
        for y in range(len(self.grid)):
            row = self.grid[y]
            if len(row) < width:
                # Extend row
                row.extend([self._empty_cell] * (width - len(row)))
            elif len(row) > width:
                # If the first discarded cell is a continuation, its head
                # would otherwise be stranded at the new right edge.
                if width > 0 and row[width][1] == CONTINUATION:
                    row[width - 1] = self._empty_cell
                # Truncate row
                self.grid[y] = row[:width]

        # Update dimensions
        self.width = width
        self.height = height

        # Every row is suspect after a reshape.
        self.row_gen = [0] * height
        self._touch_page()

    def link_extent(self, x: int, y: int) -> tuple | None:
        """The contiguous same-link run containing (x, y) on its row.

        Returns (uri, link_id, x0, x1) with an inclusive column span, or None
        if the cell isn't a link. Segments split across rows share a link_id;
        grouping those into one hover is the chrome's job.
        """
        if not (0 <= y < self.height and 0 <= x < self.width):
            return None
        row = self.grid[y]
        style = row[x][0]
        uri = style.hyperlink
        if uri is None:
            return None
        key = (uri, style.hyperlink_id)
        x0 = x
        while x0 > 0 and (row[x0 - 1][0].hyperlink, row[x0 - 1][0].hyperlink_id) == key:
            x0 -= 1
        x1 = x
        while x1 + 1 < self.width and (row[x1 + 1][0].hyperlink, row[x1 + 1][0].hyperlink_id) == key:
            x1 += 1
        return (uri, style.hyperlink_id, x0, x1)

    def get_line_text(self, y: int) -> str:
        """Get logical text, omitting width-2 continuation markers."""
        if 0 <= y < self.height:
            return "".join(cell[1] for cell in self.grid[y])
        return ""

    def get_line(self, y: int, width: int = None) -> str:
        """Get full ANSI sequence for a line — a pure read of video memory.

        No cursor or pointer is composited in; those are chrome concerns,
        rendered by the terminal from the board's registers.
        """
        if not (0 <= y < self.height):
            return ""

        # Use buffer width if not specified
        if width is None:
            width = self.width

        parts = []
        row = self.grid[y]
        current_style = Style()  # Start with default style

        # Process each cell up to specified width
        limit = min(len(row), width)
        for x in range(limit):
            cell_style, char = row[x]
            if char == CONTINUATION:
                continue
            # An explicit width may cut before a continuation that lies
            # outside the requested pane. Render a blank rather than letting
            # the wide glyph spill over its boundary.
            if x + 1 == limit and x + 1 < len(row) and row[x + 1][1] == CONTINUATION:
                char = " "
            transition = current_style.diff(cell_style)
            parts.append(transition)
            parts.append(char)
            current_style = cell_style

        # Pad to width if needed
        current_width = min(len(row), width)
        if current_width < width:
            # Transition to default style for padding
            reset_transition = current_style.diff(Style())
            parts.append(reset_transition)
            parts.append(" " * (width - current_width))
            current_style = Style()

        # Always end with a reset to prevent bleeding to next line
        final_reset = current_style.diff(Style())
        parts.append(final_reset)

        return "".join(parts)

    def get_line_tuple(self, y: int, width: int = None) -> tuple:
        """Get line as a hashable tuple for caching — a pure read of video memory."""
        if not (0 <= y < self.height):
            return tuple()

        # Use buffer width if not specified
        if width is None:
            width = self.width

        parts = []
        row = self.grid[y]

        # Process each cell up to specified width
        for x in range(min(len(row), width)):
            ansi_code, char = row[x]
            parts.extend(("ansi", ansi_code, "char", char))

        # Pad to width if needed
        current_width = min(len(row), width)
        if current_width < width:
            # Reset all attributes for padding (including background)
            parts.extend(("reset", RESET_CODE, "pad", " " * (width - current_width)))

        # Always end with a reset to prevent bleeding to next line
        parts.extend(("final_reset", RESET_CODE))

        return tuple(parts)
