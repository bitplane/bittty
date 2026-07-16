"""Cursor operation handler for the current Terminal state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..operations import Operation

if TYPE_CHECKING:
    from .board import TerminalBoard


class CursorDevice:
    """Owns cursor state and applies cursor operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.x = 0
        self.y = 0
        self.saved_x = 0
        self.saved_y = 0
        self.saved_ansi_code = ""
        self.tab_stops = set(range(8, board.width, 8))
        self.handlers = {
            "CUP": lambda op: self.move_to(*op.args),
            "HVP": lambda op: self.move_to(*op.args),
            "CUU": lambda op: self.move_up(op.args[0]),
            "CUD": lambda op: self.move_down(op.args[0]),
            "CUF": lambda op: self.move_forward(op.args[0]),
            "CUB": lambda op: self.move_back(op.args[0]),
            "CHA": lambda op: self.set_position(op.args[0], None),
            "VPA": lambda op: self.move_to(None, op.args[0]),
            "SAVE": lambda op: self.save(),
            "RESTORE": lambda op: self.restore(),
        }

    def set_position(self, x: int | None, y: int | None) -> None:
        """Move cursor to an absolute, clamped terminal position."""
        if x is not None:
            self.x = max(0, min(x, self.board.width - 1))
        if y is not None:
            self.y = max(0, min(y, self.board.height - 1))

    def move_to(self, x: int | None, y: int | None) -> None:
        """Apply a CUP/HVP/VPA move, honouring origin mode (DECOM).

        Under origin mode the row is relative to the scroll region's top and is
        clamped within the region; the column stays absolute (bittty has no
        left/right margins).
        """
        if y is not None and self.board.modes.origin_mode:
            top = self.board.screen.scroll_top
            bottom = self.board.screen.scroll_bottom
            self.set_position(x, None)
            self.y = max(top, min(top + y, bottom))
            return
        self.set_position(x, y)

    def clamp_to_terminal(self) -> None:
        """Clamp the current position after terminal dimensions change."""
        self.set_position(self.x, self.y)
        self.tab_stops = {stop for stop in self.tab_stops if stop < self.board.width}

    def move_up(self, count: int) -> None:
        self.y = max(0, self.y - count)

    def move_down(self, count: int) -> None:
        self.y = min(self.board.height - 1, self.y + count)

    def move_forward(self, count: int) -> None:
        self.x = min(self.board.width - 1, self.x + count)

    def move_back(self, count: int) -> None:
        self.x = max(0, self.x - count)

    def carriage_return(self) -> None:
        """Move cursor to the beginning of the current line."""
        self.x = 0

    def line_feed(self, is_wrapped: bool = False) -> None:
        """Move down one line, scrolling the active scroll region if needed."""
        if self.y == self.board.screen.scroll_bottom:
            self.board.screen.scroll(1)
        elif self.y < self.board.height - 1:
            # Below the bottom margin the cursor still advances (bounded by the
            # screen); it only scrolls when sitting on the margin itself.
            self.y += 1

        if self.board.modes.linefeed_newline_mode:
            self.carriage_return()

    def reverse_index(self) -> None:
        """Move up one line, scrolling down at the top of the scroll region."""
        if self.y <= self.board.screen.scroll_top:
            self.board.screen.scroll(-1)
        else:
            self.y -= 1

    def backspace(self) -> None:
        """Move cursor back one position, wrapping to the previous line if needed."""
        if self.x > 0:
            self.x -= 1
        elif self.y > 0:
            self.y -= 1
            self.x = self.board.width - 1

    def set_tab_stop(self, x: int | None = None) -> None:
        """Set a horizontal tab stop at the given column."""
        if x is None:
            x = self.x
        if 0 <= x < self.board.width:
            self.tab_stops.add(x)

    def next_tab_stop(self) -> int:
        """Return the next horizontal tab stop, clamped to the last column."""
        for stop in sorted(self.tab_stops):
            if stop > self.x:
                return min(stop, self.board.width - 1)
        return self.board.width - 1

    def horizontal_tab(self) -> None:
        """Advance to the next horizontal tab stop."""
        self.x = self.next_tab_stop()

    def prepare_for_text_write(self) -> None:
        """Apply wrapping or clipping before writing at the cursor."""
        if self.x < self.board.width:
            return
        if self.board.modes.auto_wrap:
            self.line_feed(is_wrapped=True)
            self.carriage_return()
        else:
            self.x = self.board.width - 1

    def advance_after_text_write(self, character_count: int) -> None:
        """Advance after printable text, preserving existing autowrap behavior."""
        if character_count <= 0:
            return
        if self.board.modes.auto_wrap or self.x < self.board.width - 1:
            self.x += character_count

    def save(self) -> None:
        """Save cursor position and attributes."""
        self.saved_x = self.x
        self.saved_y = self.y
        self.saved_ansi_code = self.board.style.current_ansi_code

    def restore(self) -> None:
        """Restore cursor position and attributes."""
        self.x = self.saved_x
        self.y = self.saved_y
        self.board.style.current_ansi_code = self.saved_ansi_code

    def reset(self, hard: bool = True) -> None:
        """Home the cursor and clear saved state; a hard reset restores default tab stops."""
        self.set_position(0, 0)
        self.saved_x = 0
        self.saved_y = 0
        self.saved_ansi_code = ""
        if hard:
            self.tab_stops = set(range(8, self.board.width, 8))

    def handle_operation(self, operation: Operation) -> None:
        handler = self.handlers.get(operation.name)
        if handler is not None:
            handler(operation)
