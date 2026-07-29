"""Cursor operation handler for the current board state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Device

if TYPE_CHECKING:
    from .board import Board


class CursorDevice(Device):
    """Owns cursor state and applies cursor operations."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.x = 0
        self.y = 0
        self.saved_x = 0
        self.saved_y = 0
        self.saved_ansi_code = ""
        self.shape = "block"  # block | underline | bar (DECSCUSR)
        self.tab_stops = set(range(8, board.width, 8))
        self.handlers = {
            "CUP": lambda op: self.move_to(*op.args),
            "HVP": lambda op: self.move_to(*op.args),
            "CUU": lambda op: self.move_up(op.args[0]),
            "CUD": lambda op: self.move_down(op.args[0]),
            "CUF": lambda op: self.move_forward(op.args[0]),
            "CUB": lambda op: self.move_back(op.args[0]),
            "CHA": lambda op: self.set_position(op.args[0], None),
            "HPA": lambda op: self.set_position(op.args[0], None),
            "HPR": lambda op: self.move_forward(op.args[0]),
            "VPA": lambda op: self.move_to(None, op.args[0]),
            "VPR": lambda op: self.move_down(op.args[0]),
            "CNL": lambda op: self.next_line(op.args[0]),
            "CPL": lambda op: self.previous_line(op.args[0]),
            "HPB": lambda op: self.move_back(op.args[0]),
            "VPB": lambda op: self.move_up(op.args[0]),
            "CHT": lambda op: self.forward_tab(op.args[0]),
            "CBT": lambda op: self.backward_tab(op.args[0]),
            "TBC": lambda op: self.clear_tab_stop(op.args[0]),
            "CTC": lambda op: self.tab_control(op.args[0]),
            "DECST8C": lambda op: self.reset_tab_stops(),
            "DECSCUSR": lambda op: self.set_cursor_style(op.args[0]),
            "DECBI": lambda op: self.back_index(),
            "DECFI": lambda op: self.forward_index(),
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

        Under origin mode the row is relative to the scroll region's top and the
        column to the left margin, each clamped within its margins.
        """
        if self.board.modes.origin_mode:
            screen = self.board.blitter
            if y is not None:
                self.y = max(screen.scroll_top, min(screen.scroll_top + y, screen.scroll_bottom))
            if x is not None:
                self.x = max(screen.left_margin, min(screen.left_margin + x, screen.right_margin))
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
        if self.board.printer.auto_print:  # MC auto-print: paper gets the line as we leave it
            self.board.printer.print_line(self.y)
        if self.y == self.board.blitter.scroll_bottom:
            self.board.blitter.scroll(1)
        elif self.y < self.board.height - 1:
            # Below the bottom margin the cursor still advances (bounded by the
            # screen); it only scrolls when sitting on the margin itself.
            self.y += 1

        if self.board.modes.linefeed_newline_mode:
            self.carriage_return()

    def forward_index(self) -> None:
        """DECFI — move right; at the right margin, pan the margin box one column left."""
        if self.x >= self.board.blitter.right_margin:
            self.board.blitter.pan(1)
        else:
            self.x += 1

    def back_index(self) -> None:
        """DECBI — move left; at the left margin, pan the margin box one column right."""
        if self.x <= self.board.blitter.left_margin:
            self.board.blitter.pan(-1)
        else:
            self.x -= 1

    def reverse_index(self) -> None:
        """Move up one line, scrolling down at the top of the scroll region."""
        if self.y <= self.board.blitter.scroll_top:
            self.board.blitter.scroll(-1)
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

    def previous_tab_stop(self) -> int:
        """Return the nearest tab stop left of the cursor, or column 0."""
        for stop in sorted(self.tab_stops, reverse=True):
            if stop < self.x:
                return stop
        return 0

    def forward_tab(self, count: int) -> None:
        """CHT — advance `count` tab stops."""
        for _ in range(count):
            self.horizontal_tab()

    def backward_tab(self, count: int) -> None:
        """CBT — retreat `count` tab stops."""
        for _ in range(count):
            self.x = self.previous_tab_stop()

    def clear_tab_stop(self, mode: int) -> None:
        """TBC — clear the tab stop at the cursor (0) or all tab stops (3)."""
        if mode == 3:
            self.tab_stops.clear()
        else:
            self.tab_stops.discard(self.x)

    def tab_control(self, mode: int) -> None:
        """CTC — set (0) or clear (2) a tab stop at the cursor, or clear all (5)."""
        if mode == 0:
            self.set_tab_stop()
        elif mode == 2:
            self.tab_stops.discard(self.x)
        elif mode == 5:
            self.tab_stops.clear()

    def reset_tab_stops(self) -> None:
        """DECST8C — reset to a tab stop every 8 columns."""
        self.tab_stops = set(range(8, self.board.width, 8))

    def next_line(self, count: int) -> None:
        """CNL — move to the first column, `count` lines down (no scroll)."""
        self.move_down(count)
        self.carriage_return()

    def previous_line(self, count: int) -> None:
        """CPL — move to the first column, `count` lines up (no scroll)."""
        self.move_up(count)
        self.carriage_return()

    def set_cursor_style(self, style: int) -> None:
        """DECSCUSR — set cursor shape and blink from the style parameter."""
        shapes = {0: "block", 1: "block", 2: "block", 3: "underline", 4: "underline", 5: "bar", 6: "bar"}
        self.shape = shapes.get(style, "block")
        self.board.modes.cursor_blinking = style in (0, 1, 3, 5)

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
        """Advance by terminal columns after printable text."""
        if character_count <= 0:
            return
        if self.board.modes.auto_wrap:
            self.x += character_count
        else:
            self.x = min(self.board.width - 1, self.x + character_count)

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
