"""A grid-based terminal buffer."""

from __future__ import annotations

from typing import List, Tuple

from . import constants
from .color import get_cursor_code, reset_code
from .style import Style, parse_sgr_sequence


# Type alias for a cell: (Style, character)
Cell = Tuple[Style, str]


class Buffer:
    """A 2D grid that stores terminal content."""

    def __init__(self, width: int, height: int) -> None:
        """Initialize buffer with given dimensions."""
        self.width = width
        self.height = height

        # Cache a default empty style to avoid creating new ones
        self._empty_style = Style()

        # Initialize grid with empty cells (default style, space character)
        self.grid: List[List[Cell]] = []
        for _ in range(height):
            self.grid.append(self._create_empty_row())

    def _create_empty_row(self) -> List[Cell]:
        """Create a row filled with empty cells, reusing the cached empty style."""
        return [(self._empty_style, " ") for _ in range(self.width)]

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
            if style_or_ansi is None:
                style = Style()
            elif isinstance(style_or_ansi, Style):
                style = style_or_ansi
            elif isinstance(style_or_ansi, str):
                # Parse ANSI code to Style for backward compatibility
                style = parse_sgr_sequence(style_or_ansi) if style_or_ansi else Style()
            else:
                style = Style()

            self.grid[y][x] = (style, char)

    def set(self, x: int, y: int, text: str, style_or_ansi=None) -> None:
        """Set text at position, overwriting existing content."""
        if not (0 <= y < self.height):
            return

        # Convert style_or_ansi to Style once
        if style_or_ansi is None:
            style = Style()
        elif isinstance(style_or_ansi, Style):
            style = style_or_ansi
        elif isinstance(style_or_ansi, str):
            style = parse_sgr_sequence(style_or_ansi) if style_or_ansi else Style()
        else:
            style = Style()

        for i, char in enumerate(text):
            if x + i >= self.width:
                break
            self.grid[y][x + i] = (style, char)

    def insert(self, x: int, y: int, text: str, style_or_ansi=None) -> None:
        """Insert text at position, shifting existing content right."""
        if not (0 <= y < self.height) or x >= self.width:
            return

        # Convert style_or_ansi to Style once
        if style_or_ansi is None:
            style = Style()
        elif isinstance(style_or_ansi, Style):
            style = style_or_ansi
        elif isinstance(style_or_ansi, str):
            style = parse_sgr_sequence(style_or_ansi) if style_or_ansi else Style()
        else:
            style = Style()

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
        # Convert to Style
        if style_or_ansi is None:
            style = Style()
        elif isinstance(style_or_ansi, Style):
            style = style_or_ansi
        elif isinstance(style_or_ansi, str):
            style = parse_sgr_sequence(style_or_ansi) if style_or_ansi else Style()
        else:
            style = Style()

        for y in range(max(0, y1), min(self.height, y2 + 1)):
            for x in range(max(0, x1), min(self.width, x2 + 1)):
                self.grid[y][x] = (style, " ")

    def clear_line(
        self, y: int, mode: int = constants.ERASE_FROM_CURSOR_TO_END, cursor_x: int = 0, style_or_ansi=None
    ) -> None:
        """Clear line content."""
        if not (0 <= y < self.height):
            return

        # Convert to Style
        if style_or_ansi is None:
            style = Style()
        elif isinstance(style_or_ansi, Style):
            style = style_or_ansi
        elif isinstance(style_or_ansi, str):
            style = parse_sgr_sequence(style_or_ansi) if style_or_ansi else Style()
        else:
            style = Style()

        if mode == constants.ERASE_FROM_CURSOR_TO_END:
            # Clear from cursor to end of line
            for x in range(cursor_x, self.width):
                self.grid[y][x] = (style, " ")
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            # Clear from start to cursor
            for x in range(0, min(cursor_x + 1, self.width)):
                self.grid[y][x] = (style, " ")
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

    def scroll_region_up(self, top: int, bottom: int, count: int) -> None:
        """Scroll a specific region up by count lines. BLAZING FAST bulk operation!"""
        if count <= 0 or top > bottom or bottom >= self.height:
            return

        # Clamp count to region size
        region_height = bottom - top + 1
        count = min(count, region_height)

        # Bulk slice operations - move rows up within region
        self.grid[top : bottom + 1 - count] = self.grid[top + count : bottom + 1]

        # Fill bottom of region with empty rows
        for i in range(bottom + 1 - count, bottom + 1):
            self.grid[i] = self._create_empty_row()

    def scroll_region_down(self, top: int, bottom: int, count: int) -> None:
        """Scroll a specific region down by count lines. BLAZING FAST bulk operation!"""
        if count <= 0 or top > bottom or bottom >= self.height:
            return

        # Clamp count to region size
        region_height = bottom - top + 1
        count = min(count, region_height)

        # Bulk slice operations - move rows down within region
        self.grid[top + count : bottom + 1] = self.grid[top : bottom + 1 - count]

        # Fill top of region with empty rows
        for i in range(top, top + count):
            self.grid[i] = self._create_empty_row()

    def resize(self, width: int, height: int) -> None:
        """Resize buffer to new dimensions."""
        # Adjust number of rows
        if len(self.grid) < height:
            # Add new rows
            for _ in range(height - len(self.grid)):
                self.grid.append([(Style(), " ") for _ in range(width)])
        elif len(self.grid) > height:
            # Remove excess rows
            self.grid = self.grid[:height]

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

    def get_line(
        self,
        y: int,
        width: int = None,
        cursor_x: int = -1,
        cursor_y: int = -1,
        show_cursor: bool = False,
        mouse_x: int = -1,
        mouse_y: int = -1,
        show_mouse: bool = False,
    ) -> str:
        """Get full ANSI sequence for a line."""
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

            # Handle mouse cursor (convert to 0-based, as original code does mouse_x - 1)
            if show_mouse and x == (mouse_x - 1) and y == (mouse_y - 1):
                char = "↖"

            # Handle text cursor position
            if show_cursor and x == cursor_x and y == cursor_y:
                # For cursor, we need to apply cursor style on top of cell style
                transition = current_style.diff(cell_style)
                parts.append(transition)
                parts.append(get_cursor_code())
                parts.append(char)
                parts.append("\033[27m")  # Turn off reverse video only
                current_style = cell_style  # Update tracking
            else:
                # Normal cell - generate diff from current to cell style
                transition = current_style.diff(cell_style)
                parts.append(transition)
                parts.append(char)
                current_style = cell_style  # Update tracking

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

    def get_line_tuple(
        self,
        y: int,
        width: int = None,
        cursor_x: int = -1,
        cursor_y: int = -1,
        show_cursor: bool = False,
        mouse_x: int = -1,
        mouse_y: int = -1,
        show_mouse: bool = False,
    ) -> tuple:
        """Get line as a hashable tuple for caching."""
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

            # Handle mouse cursor (convert to 0-based, as original code does mouse_x - 1)
            if show_mouse and x == (mouse_x - 1) and y == (mouse_y - 1):
                char = "↖"

            # Handle text cursor position
            if show_cursor and x == cursor_x and y == cursor_y:
                # Add cursor style
                parts.extend(("ansi", ansi_code, "cursor", get_cursor_code(), "char", char, "cursor_end", "\033[27m"))
            else:
                # Normal cell
                parts.extend(("ansi", ansi_code, "char", char))

        # Pad to width if needed
        current_width = min(len(row), width)
        if current_width < width:
            # Reset all attributes for padding (including background)
            parts.extend(("reset", reset_code(), "pad", " " * (width - current_width)))

        # Always end with a reset to prevent bleeding to next line
        parts.extend(("final_reset", reset_code()))

        return tuple(parts)
