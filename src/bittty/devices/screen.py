"""Screen and editing operation handlers for the current Terminal state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .. import constants
from ..buffer import Buffer
from ..operations import Operation

if TYPE_CHECKING:
    from .board import TerminalBoard

logger = logging.getLogger(__name__)


class ScreenDevice:
    """Owns screen buffers and applies screen/editing operations."""

    def __init__(self, board: TerminalBoard) -> None:
        self.board = board
        self.terminal = board.terminal
        self.primary_buffer = Buffer(board.width, board.height)
        self.alt_buffer = Buffer(board.width, board.height)
        self.current_buffer = self.primary_buffer
        self.in_alt_screen = False
        self.scroll_top = 0
        self.scroll_bottom = board.height - 1
        self.last_printed_char = " "

    def write_text(self, text: str, ansi_code: str = "") -> None:
        """Write printable text at the cursor position."""
        self.terminal.cursor.prepare_for_text_write()

        code_to_use = ansi_code if ansi_code else self.terminal.style.current_ansi_code
        translated_text = self.terminal.charset.translate(text)

        if self.terminal.insert_mode:
            self.current_buffer.insert(
                self.terminal.cursor_x,
                self.terminal.cursor_y,
                translated_text,
                code_to_use,
            )
        else:
            self.current_buffer.set(
                self.terminal.cursor_x,
                self.terminal.cursor_y,
                translated_text,
                code_to_use,
            )

        self.terminal.cursor.advance_after_text_write(len(translated_text))

        if translated_text:
            self.last_printed_char = translated_text[-1]

    def repeat_last_character(self, count: int) -> None:
        """Repeat the last printed character count times."""
        if count > 0 and self.last_printed_char:
            self.write_text(self.last_printed_char * count)

    def resize(self, width: int, height: int) -> None:
        """Resize terminal dimensions and screen buffers."""
        self.terminal.width = width
        self.terminal.height = height

        self.primary_buffer.resize(width, height)
        self.alt_buffer.resize(width, height)
        self.scroll_bottom = height - 1

        self.terminal.cursor.clamp_to_terminal()

    def clear_screen(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear screen."""
        bg_ansi = self.terminal.style.background_ansi()

        if mode == constants.ERASE_FROM_CURSOR_TO_END:
            self.current_buffer.clear_line(
                self.terminal.cursor_y,
                constants.ERASE_FROM_CURSOR_TO_END,
                self.terminal.cursor_x,
                bg_ansi,
            )
            for y in range(self.terminal.cursor_y + 1, self.terminal.height):
                self.current_buffer.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            for y in range(self.terminal.cursor_y):
                self.current_buffer.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
            self.clear_line(constants.ERASE_FROM_START_TO_CURSOR)
        elif mode == constants.ERASE_ALL:
            for y in range(self.terminal.height):
                self.current_buffer.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
            self.terminal.set_cursor(0, 0)

    def clear_line(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear line."""
        bg_ansi = self.terminal.style.background_ansi()
        self.current_buffer.clear_line(self.terminal.cursor_y, mode, self.terminal.cursor_x, bg_ansi)

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
        test_text = "E" * self.terminal.width
        for y in range(self.terminal.height):
            self.current_buffer.set(0, y, test_text)

    def set_scroll_region(self, top: int, bottom: int) -> None:
        """Set scroll region."""
        self.scroll_top = max(0, min(top, self.terminal.height - 1))
        self.scroll_bottom = max(self.scroll_top, min(bottom, self.terminal.height - 1))

    def insert_lines(self, count: int) -> None:
        """Insert blank lines at cursor position."""
        if count <= 0 or not (self.scroll_top <= self.terminal.cursor_y <= self.scroll_bottom):
            return

        self.current_buffer.scroll_region_down(self.terminal.cursor_y, self.scroll_bottom, count)

    def delete_lines(self, count: int) -> None:
        """Delete lines at cursor position."""
        if count <= 0 or not (self.scroll_top <= self.terminal.cursor_y <= self.scroll_bottom):
            return

        self.current_buffer.scroll_region_up(self.terminal.cursor_y, self.scroll_bottom, count)

    def insert_characters(self, count: int, ansi_code: str = "") -> None:
        """Insert blank characters at cursor position."""
        if not (0 <= self.terminal.cursor_y < self.terminal.height):
            return
        spaces = " " * count
        self.current_buffer.insert(self.terminal.cursor_x, self.terminal.cursor_y, spaces, ansi_code)

    def delete_characters(self, count: int) -> None:
        """Delete characters at cursor position."""
        if not (0 <= self.terminal.cursor_y < self.terminal.height):
            return
        self.current_buffer.delete(self.terminal.cursor_x, self.terminal.cursor_y, count)

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

    def set_column_mode(self, columns: int) -> None:
        """Set terminal width for DECCOLM."""
        if columns not in (80, 132):
            return
        if self.terminal.width == columns:
            return

        self.resize(columns, self.terminal.height)
        self.terminal.set_cursor(0, 0)

    def handle_edit_operation(self, operation: Operation) -> None:
        if operation.name == "ED":
            (mode,) = operation.args
            self.clear_screen(mode)
            return
        if operation.name == "EL":
            (mode,) = operation.args
            self.clear_line(mode)
            return
        if operation.name == "IL":
            (count,) = operation.args
            self.insert_lines(count)
            return
        if operation.name == "DL":
            (count,) = operation.args
            self.delete_lines(count)
            return
        if operation.name == "ICH":
            (count,) = operation.args
            self.insert_characters(count, self.terminal.style.current_ansi_code)
            return
        if operation.name == "DCH":
            (count,) = operation.args
            self.delete_characters(count)
            return
        if operation.name == "ECH":
            (count,) = operation.args
            for _ in range(count):
                self.current_buffer.set(
                    self.terminal.cursor_x,
                    self.terminal.cursor_y,
                    " ",
                    self.terminal.style.current_ansi_code,
                )
                if self.terminal.cursor_x < self.terminal.width - 1:
                    self.terminal.cursor_x += 1
            return
        if operation.name == "SU":
            (count,) = operation.args
            self.scroll(count)
            return
        if operation.name == "SD":
            (count,) = operation.args
            self.scroll(-count)
            return
        if operation.name == "REP":
            (count,) = operation.args
            self.repeat_last_character(count)
            return

        logger.debug("Unknown edit operation: %s", operation)

    def handle_screen_operation(self, operation: Operation) -> None:
        if operation.name == "DECSTBM":
            top, bottom = operation.args
            self.set_scroll_region(top, self.terminal.height - 1 if bottom is None else bottom)
            return
        if operation.name == "RIS":
            self.clear_screen(constants.ERASE_ALL)
            self.terminal.set_cursor(0, 0)
            self.terminal.style.reset()
            self.terminal.charset.reset()
            return

        logger.debug("Unknown screen operation: %s", operation)
