"""
Terminal Buffer: Grid-based terminal content storage.

This module provides the Buffer class that manages terminal screen content
as a 2D grid of (ansi_code, character) tuples.
"""

from __future__ import annotations

from typing import List, Tuple

from . import constants
from .color import get_cursor_code, reset_code


# Type alias for a cell: (ANSI code, character)
Cell = Tuple[str, str]


class Buffer:
    """
    A buffer that stores terminal content as a 2D grid.

    Each cell contains a tuple of (ansi_code, character) where:
    - ansi_code: ANSI escape sequence for styling (empty string for no styling)
    - character: The actual character to display
    """

    def __init__(self, width: int, height: int) -> None:
        """Initialize buffer with given dimensions."""
        self.width = width
        self.height = height
        # Initialize grid with empty cells
        self.grid: List[List[Cell]] = [[("", " ") for _ in range(width)] for _ in range(height)]

    def get_content(self) -> List[List[Cell]]:
        """Get buffer content as a 2D grid."""
        return [row[:] for row in self.grid]

    def get_cell(self, x: int, y: int) -> Cell:
        """Get cell at position."""
        if 0 <= y < self.height and 0 <= x < self.width:
            return self.grid[y][x]
        return ("", " ")

    def set_cell(self, x: int, y: int, char: str, ansi_code: str = "") -> None:
        """Set a single cell at position."""
        if 0 <= y < self.height and 0 <= x < self.width:
            self.grid[y][x] = (ansi_code, char)

    def set(self, x: int, y: int, text: str, ansi_code: str = "") -> None:
        """Set text at position, overwriting existing content."""
        if not (0 <= y < self.height):
            return

        for i, char in enumerate(text):
            if x + i >= self.width:
                break
            self.grid[y][x + i] = (ansi_code, char)

    def insert(self, x: int, y: int, text: str, ansi_code: str = "") -> None:
        """Insert text at position, shifting existing content right."""
        if not (0 <= y < self.height) or x >= self.width:
            return

        # Get the current row
        row = self.grid[y]

        # Create new cells for the inserted text
        new_cells = [(ansi_code, char) for char in text]

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
                row.extend([("", " ")] * padding_needed)
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
                new_row.append(("", " "))
            self.grid[y] = new_row

    def clear_region(self, x1: int, y1: int, x2: int, y2: int, ansi_code: str = "") -> None:
        """Clear a rectangular region."""
        for y in range(max(0, y1), min(self.height, y2 + 1)):
            for x in range(max(0, x1), min(self.width, x2 + 1)):
                self.grid[y][x] = (ansi_code, " ")

    def clear_line(
        self, y: int, mode: int = constants.ERASE_FROM_CURSOR_TO_END, cursor_x: int = 0, ansi_code: str = ""
    ) -> None:
        """Clear line content."""
        if not (0 <= y < self.height):
            return

        if mode == constants.ERASE_FROM_CURSOR_TO_END:
            # Clear from cursor to end of line
            for x in range(cursor_x, self.width):
                self.grid[y][x] = (ansi_code, " ")
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            # Clear from start to cursor
            for x in range(0, min(cursor_x + 1, self.width)):
                self.grid[y][x] = (ansi_code, " ")
        elif mode == constants.ERASE_ALL:
            # Clear entire line
            self.grid[y] = [(ansi_code, " ") for _ in range(self.width)]

    def scroll_up(self, count: int) -> None:
        """Scroll content up, removing top lines and adding blank lines at bottom."""
        for _ in range(count):
            self.grid.pop(0)
            self.grid.append([("", " ") for _ in range(self.width)])

    def scroll_down(self, count: int) -> None:
        """Scroll content down, removing bottom lines and adding blank lines at top."""
        for _ in range(count):
            self.grid.pop()
            self.grid.insert(0, [("", " ") for _ in range(self.width)])

    def resize(self, width: int, height: int) -> None:
        """Resize buffer to new dimensions."""
        # Adjust number of rows
        if len(self.grid) < height:
            # Add new rows
            for _ in range(height - len(self.grid)):
                self.grid.append([("", " ") for _ in range(width)])
        elif len(self.grid) > height:
            # Remove excess rows
            self.grid = self.grid[:height]

        # Adjust width of each row
        for y in range(len(self.grid)):
            row = self.grid[y]
            if len(row) < width:
                # Extend row
                row.extend([("", " ")] * (width - len(row)))
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
        """Get full ANSI sequence for a line (like tmux capture-pane)."""
        if not (0 <= y < self.height):
            return ""

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
                parts.append(ansi_code)
                parts.append(get_cursor_code())
                parts.append(char)
                parts.append("\033[27m")  # Turn off reverse video only
            else:
                # Normal cell
                parts.append(ansi_code)
                parts.append(char)

        # Pad to width if needed
        current_width = min(len(row), width)
        if current_width < width:
            # Reset all attributes for padding (including background)
            parts.append(reset_code())
            parts.append(" " * (width - current_width))

        # Always end with a reset to prevent bleeding to next line
        parts.append(reset_code())

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
        """Get line as hashable tuple for caching: (ansi_code, char, ansi_code, char, ...)"""
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
