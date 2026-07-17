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

    def _create_empty_row(self) -> List[Cell]:
        """Create a row filled with the shared empty cell (list-multiply, no per-cell build)."""
        return [self._empty_cell] * self.width

    def set_line_attribute(self, y: int, attribute: str) -> None:
        """Set a line's DECDHL/DECDWL/DECSWL attribute."""
        if 0 <= y < self.height:
            self.line_attributes[y] = attribute

    def get_line_attribute(self, y: int) -> str:
        """Return a line's width/height attribute (single by default)."""
        if 0 <= y < self.height:
            return self.line_attributes[y]
        return constants.LINE_SINGLE

    def reset_line_attributes(self) -> None:
        """Return every line to single-width, single-height (RIS)."""
        self.line_attributes = [constants.LINE_SINGLE] * self.height

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

    def set(self, x: int, y: int, text: str, style_or_ansi=None) -> None:
        """Set text at position, overwriting existing content."""
        if not (0 <= y < self.height):
            return

        style = _coerce_style(style_or_ansi)

        end = min(x + len(text), self.width)
        if end <= x:
            return
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

    def clear_region(self, x1: int, y1: int, x2: int, y2: int, style_or_ansi=None) -> None:
        """Clear a rectangular region."""
        style = _coerce_style(style_or_ansi)

        left, right = max(0, x1), min(self.width, x2 + 1)
        if right <= left:
            return
        blanks = [(style, " ")] * (right - left)
        for y in range(max(0, y1), min(self.height, y2 + 1)):
            self.grid[y][left:right] = blanks

    def clear_line(
        self, y: int, mode: int = constants.ERASE_FROM_CURSOR_TO_END, cursor_x: int = 0, style_or_ansi=None
    ) -> None:
        """Clear line content."""
        if not (0 <= y < self.height):
            return

        style = _coerce_style(style_or_ansi)

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

    def resize(self, width: int, height: int) -> None:
        """Resize buffer to new dimensions."""
        # Adjust number of rows
        if len(self.grid) < height:
            # Add new rows
            for _ in range(height - len(self.grid)):
                self.grid.append([(Style(), " ") for _ in range(width)])
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
                row.extend([(Style(), " ")] * (width - len(row)))
            elif len(row) > width:
                # Truncate row
                self.grid[y] = row[:width]

        # Update dimensions
        self.width = width
        self.height = height

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
