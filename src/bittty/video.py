"""Video memory: the 2D cell grid the blitter writes and terminals render.

A Board has two pages of it (primary and alternate).
"""

from __future__ import annotations

from typing import List, Tuple

from . import constants
from .style import Style, parse_sgr_sequence, RESET_CODE


# Type alias for a cell: (Style, character)
Cell = Tuple[Style, str]


def _coerce_style(style_or_ansi) -> Style:
    """Normalise a Style | ANSI-string | None argument to a Style."""
    if isinstance(style_or_ansi, Style):
        return style_or_ansi
    if isinstance(style_or_ansi, str) and style_or_ansi:
        return parse_sgr_sequence(style_or_ansi)
    return Style()


class Video:
    """A 2D grid that stores terminal content."""

    def __init__(self, width: int, height: int) -> None:
        """Initialize buffer with given dimensions."""
        self.width = width
        self.height = height

        # Cache a default empty style + cell to avoid rebuilding them (cells are
        # immutable tuples, always replaced never mutated, so one instance is safe to share).
        self._empty_style = Style()
        self._empty_cell: Cell = (self._empty_style, " ")

        # Initialize grid with empty cells (default style, space character)
        self.grid: List[List[Cell]] = []
        for _ in range(height):
            self.grid.append(self._create_empty_row())

        # Per-line DECDHL/DECDWL/DECSWL attribute, kept parallel to grid rows.
        self.line_attributes: List[str] = [constants.LINE_SINGLE] * height

        # Dirty tracking: readers own the clock. Writes stamp the CURRENT
        # epoch (one store — no increment on the hot path); a renderer calls
        # observe() to open a new epoch after it snapshots. Targeted writes
        # stamp their row in row_gen; whole-page upheavals (full scroll,
        # resize) stamp page_gen instead of touching every row.
        self.generation = 1
        self.page_gen = 0
        self.row_gen: List[int] = [0] * height

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

    def dirty_rows(self, seen: int) -> List[int]:
        """Rows changed since `seen` (a value returned by observe())."""
        if self.page_gen >= seen:
            return list(range(self.height))
        return [y for y, g in enumerate(self.row_gen) if g >= seen]

    def _create_empty_row(self, width: int | None = None) -> List[Cell]:
        """Create a row filled with the shared empty cell (list-multiply, no per-cell build)."""
        return [self._empty_cell] * (self.width if width is None else width)

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

    def get_content(self) -> List[List[Cell]]:
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
        if 0 <= y < self.height and 0 <= x < self.width:
            self.grid[y][x] = (_coerce_style(style_or_ansi), char)
            self._touch_row(y)

    def set(self, x: int, y: int, text: str, style_or_ansi=None) -> None:
        """Set text at position, overwriting existing content."""
        if not (0 <= y < self.height):
            return

        style = _coerce_style(style_or_ansi)

        end = min(x + len(text), self.width)
        if end <= x:
            return
        self.row_gen[y] = self.generation
        if end - x == 1:  # single cell (the common case for TUI repaints)
            self.grid[y][x] = (style, text[0])
            return
        self.grid[y][x:end] = [(style, char) for char in text[: end - x]]

    def insert(self, x: int, y: int, text: str, style_or_ansi=None) -> None:
        """Insert text at position, shifting existing content right."""
        if not (0 <= y < self.height) or x >= self.width:
            return

        style = _coerce_style(style_or_ansi)

        # Get the current row
        row = self.grid[y]

        # Create new cells for the inserted text
        new_cells = [(style, char) for char in text]

        # Insert at position
        if x < len(row):
            # Split row and insert
            new_row = row[:x] + new_cells + row[x:]
            # Truncate to width
            self.grid[y] = new_row[: self.width]
        else:
            # Pad with spaces if needed
            padding_needed = x - len(row)
            if padding_needed > 0:
                row.extend([(Style(), " ")] * padding_needed)
            row.extend(new_cells)
            # Truncate to width
            self.grid[y] = row[: self.width]
        self._touch_row(y)

    def delete(self, x: int, y: int, count: int = 1) -> None:
        """Delete characters at position."""
        if not (0 <= y < self.height) or x >= self.width:
            return

        row = self.grid[y]

        # Delete characters and shift left
        if x < len(row):
            end_pos = min(x + count, len(row))
            new_row = row[:x] + row[end_pos:]
            # Pad with spaces to maintain width
            while len(new_row) < self.width:
                new_row.append((Style(), " "))
            self.grid[y] = new_row
            self._touch_row(y)

    def clear_region(self, x1: int, y1: int, x2: int, y2: int, style_or_ansi=None) -> None:
        """Clear a rectangular region."""
        style = _coerce_style(style_or_ansi)

        left, right = max(0, x1), min(self.width, x2 + 1)
        if right <= left:
            return
        blanks = [(style, " ")] * (right - left)
        g = self.generation
        for y in range(max(0, y1), min(self.height, y2 + 1)):
            self.grid[y][left:right] = blanks
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
            # Clear from cursor to end of line
            if cursor_x < self.width:
                self.grid[y][cursor_x : self.width] = [(style, " ")] * (self.width - cursor_x)
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            # Clear from start to cursor
            n = min(cursor_x + 1, self.width)
            self.grid[y][:n] = [(style, " ")] * n
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

    def scroll_region_up(self, top: int, bottom: int, count: int) -> None:
        """Scroll a specific region up by count lines. BLAZING FAST bulk operation!"""
        if count <= 0 or top > bottom or bottom >= self.height:
            return

        # Clamp count to region size
        region_height = bottom - top + 1
        count = min(count, region_height)

        # Bulk slice operations - move rows up within region
        self.grid[top : bottom + 1 - count] = self.grid[top + count : bottom + 1]
        self.line_attributes[top : bottom + 1 - count] = self.line_attributes[top + count : bottom + 1]

        # Fill bottom of region with empty rows
        for i in range(bottom + 1 - count, bottom + 1):
            self.grid[i] = self._create_empty_row()
            self.line_attributes[i] = constants.LINE_SINGLE

        self._touch_scrolled(top, bottom)

    def scroll_region_down(self, top: int, bottom: int, count: int) -> None:
        """Scroll a specific region down by count lines. BLAZING FAST bulk operation!"""
        if count <= 0 or top > bottom or bottom >= self.height:
            return

        # Clamp count to region size
        region_height = bottom - top + 1
        count = min(count, region_height)

        # Bulk slice operations - move rows down within region
        self.grid[top + count : bottom + 1] = self.grid[top : bottom + 1 - count]
        self.line_attributes[top + count : bottom + 1] = self.line_attributes[top : bottom + 1 - count]

        # Fill top of region with empty rows
        for i in range(top, top + count):
            self.grid[i] = self._create_empty_row()
            self.line_attributes[i] = constants.LINE_SINGLE

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
        """Get plain text content of a line (for debugging/testing)."""
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
        for x in range(min(len(row), width)):
            cell_style, char = row[x]
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
