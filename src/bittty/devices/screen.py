"""Screen and editing operation handlers for the current Terminal state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import constants
from ..buffer import Buffer
from ..operations import Operation

if TYPE_CHECKING:
    from .board import TerminalBoard


class ScreenDevice:
    """Owns screen buffers and applies screen/editing operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.primary_buffer = Buffer(board.width, board.height)
        self.alt_buffer = Buffer(board.width, board.height)
        self.current_buffer = self.primary_buffer
        self.in_alt_screen = False
        self.scroll_top = 0
        self.scroll_bottom = board.height - 1
        self.last_printed_char = " "
        self.handlers = {
            "ED": lambda op: self.clear_screen(op.args[0]),
            "EL": lambda op: self.clear_line(op.args[0]),
            "IL": lambda op: self.insert_lines(op.args[0]),
            "DL": lambda op: self.delete_lines(op.args[0]),
            "ICH": lambda op: self.insert_characters(op.args[0], self.board.style.current),
            "DCH": lambda op: self.delete_characters(op.args[0]),
            "ECH": lambda op: self.erase_characters(op.args[0]),
            "SU": lambda op: self.scroll(op.args[0]),
            "SD": lambda op: self.scroll(-op.args[0]),
            "REP": lambda op: self.repeat_last_character(op.args[0]),
            "DECSTBM": lambda op: self.set_scroll_region(
                op.args[0], self.board.height - 1 if op.args[1] is None else op.args[1]
            ),
            "RIS": lambda op: self.board.reset(hard=True),
            "DECSTR": lambda op: self.board.reset(hard=False),
            "DECALN": lambda op: self.alignment_test(),
        }

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

    def scroll_up(self, count: int) -> None:
        """Scroll content up within scroll region."""
        self.scroll(count)

    def scroll_down(self, count: int) -> None:
        """Scroll content down within scroll region."""
        self.scroll(-count)

    def reset(self, hard: bool = True) -> None:
        """Restore the full scroll region; a hard reset also clears both buffers to primary."""
        self.set_scroll_region(0, self.board.height - 1)
        if not hard:
            return
        self.in_alt_screen = False
        self.current_buffer = self.primary_buffer
        for buf in (self.primary_buffer, self.alt_buffer):
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

    def handle_operation(self, operation: Operation) -> None:
        handler = self.handlers.get(operation.name)
        if handler is not None:
            handler(operation)
