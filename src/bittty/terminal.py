"""
A terminal emulator.

UI frameworks can subclass this to create terminal widgets.
"""

from __future__ import annotations

import sys
import asyncio
import subprocess
from typing import Any, Optional, Callable

import logging

from .buffer import Buffer
from .parser import Parser
from . import constants
from .style import get_background
from .charsets import get_charset

logger = logging.getLogger(__name__)


class Terminal:
    """
    A terminal emulator with process management and screen buffers.

    This class handles all terminal logic but has no UI dependencies.
    Subclass this to create terminal widgets for specific UI frameworks.
    """

    @staticmethod
    def get_pty_handler(
        rows: int = constants.DEFAULT_TERMINAL_HEIGHT,
        cols: int = constants.DEFAULT_TERMINAL_WIDTH,
        stdin=None,
        stdout=None,
    ):
        """Create a platform-appropriate PTY handler."""
        if stdin is not None and stdout is not None:
            from .pty import StdioPTY

            return StdioPTY(stdin, stdout, rows, cols)
        elif sys.platform == "win32":
            from .pty import WindowsPTY

            return WindowsPTY(rows, cols)
        else:
            from .pty import UnixPTY

            return UnixPTY(rows, cols)

    def __init__(
        self,
        command: str = "/bin/bash",
        width: int = 80,
        height: int = 24,
        stdin=None,
        stdout=None,
    ) -> None:
        """Initialize terminal."""
        self.command = command
        self.width = width
        self.height = height
        self.stdin = stdin
        self.stdout = stdout

        # Terminal state - these can be made reactive in subclasses
        self.title = "Terminal"
        self.icon_title = "Terminal"
        self.cursor_x = 0
        self.cursor_y = 0
        self.cursor_visible = True

        # Mouse position
        self.mouse_x = 0
        self.mouse_y = 0

        self.show_mouse = False

        # Terminal modes
        self.auto_wrap = True
        self.insert_mode = False
        self.application_keypad = False
        self.cursor_application_mode = False
        self.scroll_mode = False
        self.mouse_tracking = False
        self.mouse_button_tracking = False
        self.mouse_any_tracking = False
        self.mouse_sgr_mode = False
        self.mouse_extended_mode = False
        self.backarrow_key_sends_bs = False  # DECBKM: False = sends DEL, True = sends BS
        self.scroll_mode = False  # DECSCLM: False = jump scrolling, True = smooth scrolling
        self.auto_repeat = True  # DECARM: True = auto-repeat enabled, False = disabled
        self.numeric_keypad = True  # DECNKM: True = numeric mode, False = application mode
        self.local_echo = True  # SRM: True = echo enabled, False = echo disabled
        self.reverse_screen = False  # DECSCNM: False = normal, True = reverse video
        self.linefeed_newline_mode = False  # DECNLM: False = LF only, True = CR+LF
        self.origin_mode = False  # DECOM: False = absolute, True = relative to scroll region
        self.auto_resize_mode = False  # DECARSM: False = manual, True = auto-resize
        self.keyboard_usage_mode = False  # DECKBUM: False = normal, True = typewriter mode

        # Screen buffers
        self.primary_buffer = Buffer(width, height)  # With scrollback (future)
        self.alt_buffer = Buffer(width, height)  # No scrollback
        self.current_buffer = self.primary_buffer
        self.in_alt_screen = False

        # Scroll region (top, bottom) - 0-indexed
        self.scroll_top = 0
        self.scroll_bottom = height - 1

        # Current ANSI code for next write
        self.current_ansi_code: str = ""

        # Last printed character (for REP command)
        self.last_printed_char = " "

        # Character set state (G0-G3 sets)
        self.g0_charset = "B"  # Default: US ASCII
        self.g1_charset = "B"  # Default: US ASCII
        self.g2_charset = "B"  # Default: US ASCII
        self.g3_charset = "B"  # Default: US ASCII
        self.current_charset = 0  # 0 = G0, 1 = G1, 2 = G2, 3 = G3
        self.single_shift = None  # For SS2/SS3 (temporary shift)

        # Saved cursor state (for DECSC/DECRC)
        self.saved_cursor_x = 0
        self.saved_cursor_y = 0
        self.saved_ansi_code: str = ""

        # Process management
        self.process: Optional[subprocess.Popen] = None
        self.pty: Optional[Any] = None
        self._pty_reader_task: Optional[asyncio.Task] = None

        # PTY data callback for async handling
        self._pty_data_callback: Optional[Callable[[str], None]] = None

        # Parser
        self.parser = Parser(self)

    def set_pty_data_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for handling PTY data asynchronously."""
        self._pty_data_callback = callback

    def _process_pty_data_sync(self, data: str) -> None:
        """Process PTY data synchronously (fallback)."""
        self.parser.feed(data)

    def resize(self, width: int, height: int) -> None:
        """Resize terminal to new dimensions."""
        self.width = width
        self.height = height

        # Resize both buffers
        self.primary_buffer.resize(width, height)
        self.alt_buffer.resize(width, height)

        # Adjust scroll region
        self.scroll_bottom = height - 1

        # Clamp cursor position
        self.cursor_x = min(self.cursor_x, width - 1)
        self.cursor_y = min(self.cursor_y, height - 1)

        # Resize PTY if running
        if self.pty is not None:
            self.pty.resize(height, width)

    def get_content(self):
        """Get current screen content as raw buffer data."""
        return self.current_buffer.get_content()

    def capture_pane(self) -> str:
        """Capture terminal content."""
        lines = []
        for y in range(self.height):
            lines.append(
                self.current_buffer.get_line(
                    y,
                    width=self.width,
                    cursor_x=self.cursor_x,
                    cursor_y=self.cursor_y,
                    show_cursor=self.cursor_visible,
                    mouse_x=self.mouse_x,
                    mouse_y=self.mouse_y,
                    show_mouse=self.show_mouse,
                )
            )
        return "\n".join(lines)

    # Methods called by parser
    def write_text(self, text: str, ansi_code: str = "") -> None:
        """Write text at cursor position."""
        # Handle line wrapping or clipping
        if self.cursor_x >= self.width:
            if self.auto_wrap:
                self.line_feed(is_wrapped=True)
                self.cursor_x = 0
            else:
                self.cursor_x = self.width - 1

        # Use provided ANSI code or current one
        code_to_use = ansi_code if ansi_code else self.current_ansi_code

        # Translate characters if using DEC Special Graphics
        translated_text = self._translate_charset(text)

        # Insert or overwrite based on mode
        if self.insert_mode:
            self.current_buffer.insert(self.cursor_x, self.cursor_y, translated_text, code_to_use)
        else:
            self.current_buffer.set(self.cursor_x, self.cursor_y, translated_text, code_to_use)

        # Move cursor forward by character count
        if self.auto_wrap or self.cursor_x < self.width - 1:
            self.cursor_x += len(translated_text)

        # Remember last character for REP command
        if translated_text:
            self.last_printed_char = translated_text[-1]

    def _translate_charset(self, text: str) -> str:
        """Translate characters based on current character set."""
        result = []

        for char in text:
            # Check for single shift (SS2/SS3) - takes precedence
            if self.single_shift is not None:
                charset_designator = [self.g0_charset, self.g1_charset, self.g2_charset, self.g3_charset][
                    self.single_shift
                ]
                self.single_shift = None  # Reset after one character
            else:
                # Use current charset
                charset_designator = [self.g0_charset, self.g1_charset, self.g2_charset, self.g3_charset][
                    self.current_charset
                ]

            # Get the character mapping for this charset
            charset_map = get_charset(charset_designator)
            translated_char = charset_map.get(char, char)
            result.append(translated_char)

        return "".join(result)

    def set_g0_charset(self, charset: str) -> None:
        """Set the G0 character set."""
        self.g0_charset = charset

    def set_g1_charset(self, charset: str) -> None:
        """Set the G1 character set."""
        self.g1_charset = charset

    def set_g2_charset(self, charset: str) -> None:
        """Set the G2 character set."""
        self.g2_charset = charset

    def set_g3_charset(self, charset: str) -> None:
        """Set the G3 character set."""
        self.g3_charset = charset

    def shift_in(self) -> None:
        """Shift In (SI) - switch to G0."""
        self.current_charset = 0

    def shift_out(self) -> None:
        """Shift Out (SO) - switch to G1."""
        self.current_charset = 1

    def single_shift_2(self) -> None:
        """Single Shift 2 (SS2) - use G2 for next character only."""
        self.single_shift = 2

    def single_shift_3(self) -> None:
        """Single Shift 3 (SS3) - use G3 for next character only."""
        self.single_shift = 3

    def move_cursor(self, x: Optional[int], y: Optional[int]) -> None:
        """Move cursor to position."""
        if x is not None:
            self.cursor_x = max(0, min(x, self.width - 1))
        if y is not None:
            self.cursor_y = max(0, min(y, self.height - 1))

    def line_feed(self, is_wrapped: bool = False) -> None:
        """Perform line feed, with optional carriage return if DECNLM is enabled."""
        if self.cursor_y == self.scroll_bottom:
            # At bottom of scroll region - scroll up
            self.scroll(1)
        elif self.cursor_y < self.scroll_bottom:
            # Not at bottom yet - move cursor down
            self.cursor_y += 1
        # If cursor is somehow beyond scroll_bottom, don't move it further

        # DECNLM: When enabled, line feed also performs carriage return
        if self.linefeed_newline_mode:
            self.cursor_x = 0

    def carriage_return(self) -> None:
        """Move cursor to beginning of line."""
        self.cursor_x = 0

    def backspace(self) -> None:
        """Move cursor back one position."""
        if self.cursor_x > 0:
            self.cursor_x -= 1
        elif self.cursor_y > 0:
            # Wrap to end of previous line
            self.cursor_y -= 1
            self.cursor_x = self.width - 1

    def clear_screen(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear screen."""
        # Get just the background color from current style
        bg_ansi = get_background(self.current_ansi_code)

        if mode == constants.ERASE_FROM_CURSOR_TO_END:
            # Clear current line from cursor to end
            self.current_buffer.clear_line(self.cursor_y, constants.ERASE_FROM_CURSOR_TO_END, self.cursor_x, bg_ansi)
            # Clear all lines below cursor
            for y in range(self.cursor_y + 1, self.height):
                self.current_buffer.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
        elif mode == constants.ERASE_FROM_START_TO_CURSOR:
            # Clear all lines above cursor
            for y in range(self.cursor_y):
                self.current_buffer.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
            self.clear_line(constants.ERASE_FROM_START_TO_CURSOR)
        elif mode == constants.ERASE_ALL:
            for y in range(self.height):
                self.current_buffer.clear_line(y, constants.ERASE_ALL, 0, bg_ansi)
            self.cursor_x = 0
            self.cursor_y = 0

    def clear_line(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear line."""
        # Get just the background color from current style
        bg_ansi = get_background(self.current_ansi_code)
        self.current_buffer.clear_line(self.cursor_y, mode, self.cursor_x, bg_ansi)

    def clear_rect(self, x1: int, y1: int, x2: int, y2: int, ansi_code: str = "") -> None:
        """Clear a rectangular region."""
        self.current_buffer.clear_region(x1, y1, x2, y2, ansi_code)

    def alternate_screen_on(self) -> None:
        """Switch to alternate screen."""
        self.switch_screen(True)

    def alternate_screen_off(self) -> None:
        """Switch to primary screen."""
        self.switch_screen(False)

    def set_mode(self, mode: int, value: bool = True, private: bool = False) -> None:
        """Set terminal mode."""
        if private:
            if mode == constants.DECAWM_AUTOWRAP:
                self.auto_wrap = value
            elif mode == constants.DECTCEM_SHOW_CURSOR:
                self.cursor_visible = value
            elif mode == constants.MOUSE_TRACKING_BASIC:
                self.mouse_tracking = value
            elif mode == constants.MOUSE_TRACKING_BUTTON_EVENT:
                self.mouse_button_tracking = value
            elif mode == constants.MOUSE_TRACKING_ANY_EVENT:
                self.mouse_any_tracking = value
            elif mode == constants.MOUSE_SGR_MODE:
                self.mouse_sgr_mode = value
            elif mode == constants.MOUSE_EXTENDED_MODE:
                self.mouse_extended_mode = value
        else:
            if mode == constants.IRM_INSERT_REPLACE:
                self.insert_mode = value
            elif mode == constants.DECKPAM_APPLICATION_KEYPAD:
                self.application_keypad = value

    def clear_mode(self, mode, private: bool = False) -> None:
        """Clear terminal mode."""
        self.set_mode(mode, False, private)

    def switch_screen(self, alt: bool) -> None:
        """Switch between primary and alternate screen."""
        if alt and not self.in_alt_screen:
            # Switch to alt screen
            self.current_buffer = self.alt_buffer
            self.in_alt_screen = True
        elif not alt and self.in_alt_screen:
            # Switch to primary screen
            self.current_buffer = self.primary_buffer
            self.in_alt_screen = False

    def set_title(self, title: str) -> None:
        """Set terminal title."""
        self.title = title

    def set_icon_title(self, icon_title: str) -> None:
        """Set terminal icon title."""
        self.icon_title = icon_title

    def bell(self) -> None:
        """Terminal bell."""
        pass  # Subclasses can override

    def alignment_test(self) -> None:
        """Fill the screen with 'E' characters for alignment testing."""
        test_text = "E" * self.width
        for y in range(self.height):
            self.current_buffer.set(0, y, test_text)

    def save_cursor(self) -> None:
        """Save cursor position and attributes."""
        self.saved_cursor_x = self.cursor_x
        self.saved_cursor_y = self.cursor_y
        self.saved_ansi_code = self.current_ansi_code

    def restore_cursor(self) -> None:
        """Restore cursor position and attributes."""
        self.cursor_x = self.saved_cursor_x
        self.cursor_y = self.saved_cursor_y
        self.current_ansi_code = self.saved_ansi_code

    def set_scroll_region(self, top: int, bottom: int) -> None:
        """Set scroll region."""
        self.scroll_top = max(0, min(top, self.height - 1))
        self.scroll_bottom = max(self.scroll_top, min(bottom, self.height - 1))

    def insert_lines(self, count: int) -> None:
        """Insert blank lines at cursor position."""
        for _ in range(count):
            # Shift lines down and clear current line
            for y in range(self.height - 1, self.cursor_y, -1):
                if y - 1 >= 0:
                    # Copy line above to current line
                    for x in range(self.width):
                        cell = self.current_buffer.get_cell(x, y - 1)
                        self.current_buffer.set_cell(x, y, cell[1], cell[0])
            # Clear the current line
            self.current_buffer.clear_line(self.cursor_y, constants.ERASE_ALL)

    def delete_lines(self, count: int) -> None:
        """Delete lines at cursor position."""
        for _ in range(count):
            # Shift lines up
            for y in range(self.cursor_y, self.height - 1):
                if y + 1 < self.height:
                    # Copy line below to current line
                    for x in range(self.width):
                        cell = self.current_buffer.get_cell(x, y + 1)
                        self.current_buffer.set_cell(x, y, cell[1], cell[0])
            # Clear the bottom line
            self.current_buffer.clear_line(self.height - 1, constants.ERASE_ALL)

    def insert_characters(self, count: int, ansi_code: str = "") -> None:
        """Insert blank characters at cursor position."""
        if not (0 <= self.cursor_y < self.height):
            return
        spaces = " " * count
        self.current_buffer.insert(self.cursor_x, self.cursor_y, spaces, ansi_code)

    def delete_characters(self, count: int) -> None:
        """Delete characters at cursor position."""
        if not (0 <= self.cursor_y < self.height):
            return
        self.current_buffer.delete(self.cursor_x, self.cursor_y, count)

    def scroll(self, lines: int) -> None:
        """Centralized scrolling method that enforces scroll region boundaries.

        Args:
            lines: Number of lines to scroll. Positive = up, negative = down.
        """
        if lines == 0 or self.scroll_top > self.scroll_bottom:
            return

        # Get just the background color from current style for clearing
        bg_ansi = get_background(self.current_ansi_code)

        abs_lines = abs(lines)

        for _ in range(abs_lines):
            if lines > 0:
                # Scroll up - content moves up, new line appears at bottom
                # Shift lines up within scroll region only
                for y in range(self.scroll_top, self.scroll_bottom):
                    for x in range(self.width):
                        if y + 1 <= self.scroll_bottom:
                            cell = self.current_buffer.get_cell(x, y + 1)
                            self.current_buffer.set_cell(x, y, cell[1], cell[0])
                        else:
                            # Clear the cell if we can't copy from below
                            self.current_buffer.set_cell(x, y, bg_ansi, " ")
                # Clear the bottom line of the scroll region
                self.current_buffer.clear_line(self.scroll_bottom, constants.ERASE_ALL, 0, bg_ansi)

            else:  # lines < 0
                # Scroll down - content moves down, new line appears at top
                # Shift lines down within scroll region only
                for y in range(self.scroll_bottom, self.scroll_top, -1):
                    for x in range(self.width):
                        if y - 1 >= self.scroll_top:
                            cell = self.current_buffer.get_cell(x, y - 1)
                            self.current_buffer.set_cell(x, y, cell[1], cell[0])
                        else:
                            # Clear the cell if we can't copy from above
                            self.current_buffer.set_cell(x, y, bg_ansi, " ")
                # Clear the top line of the scroll region
                self.current_buffer.clear_line(self.scroll_top, constants.ERASE_ALL, 0, bg_ansi)

    def scroll_up(self, count: int) -> None:
        """Scroll content up within scroll region."""
        self.scroll(count)

    def scroll_down(self, count: int) -> None:
        """Scroll content down within scroll region."""
        self.scroll(-count)

    def set_cursor(self, x: Optional[int], y: Optional[int]) -> None:
        """Set cursor position (alias for move_cursor)."""
        self.move_cursor(x, y)

    def set_column_mode(self, columns: int) -> None:
        """Set terminal width for DECCOLM (column mode).

        Args:
            columns: 80 for normal mode, 132 for wide mode
        """
        if columns not in (80, 132):
            return  # Invalid column count, ignore

        # Only change if different
        if self.width == columns:
            return

        # Update terminal width
        self.width = columns

        # Resize buffers to new width
        self.primary_buffer.resize(columns, self.height)
        self.alt_buffer.resize(columns, self.height)

        # Move cursor to home position (required by DECCOLM spec)
        self.cursor_x = 0
        self.cursor_y = 0

    def repeat_last_character(self, count: int) -> None:
        """Repeat the last printed character count times (REP command)."""
        if count > 0 and self.last_printed_char:
            repeated_text = self.last_printed_char * count
            self.write_text(repeated_text)

    # Input handling methods
    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert key + modifier to standard control codes, then send to input()."""
        # Handle cursor keys (up, down, left, right)
        if char in constants.CURSOR_KEYS:
            if modifier == constants.KEY_MOD_NONE:
                # Simple cursor keys - send standard sequences
                sequence = f"{constants.ESC}[{constants.CURSOR_KEYS[char]}"
            else:
                # Modified cursor keys - CSI format with modifier
                sequence = f"{constants.ESC}[1;{modifier}{constants.CURSOR_KEYS[char]}"
            self.input(sequence)
            return

        # Handle navigation keys (home, end)
        if char in constants.NAV_KEYS:
            if modifier == constants.KEY_MOD_NONE:
                sequence = f"{constants.ESC}[{constants.NAV_KEYS[char]}"
            else:
                sequence = f"{constants.ESC}[1;{modifier}{constants.NAV_KEYS[char]}"
            self.input(sequence)
            return

        # Handle backspace key (DECBKM mode)
        if char == constants.BS:
            if self.backarrow_key_sends_bs:
                self.input(constants.BS)  # Send BS (0x08)
            else:
                self.input(constants.DEL)  # Send DEL (0x7F) - default
            return

        # Handle control characters (Ctrl+A = \x01, etc.)
        if modifier == constants.KEY_MOD_CTRL and len(char) == 1:
            upper_char = char.upper()
            if "A" <= upper_char <= "Z":
                control_char = chr(ord(upper_char) - ord("A") + 1)
                self.input(control_char)
                return

        # Handle regular printable characters
        if len(char) == 1 and char.isprintable():
            self.input(char)
            return

        # Fallback: send any unhandled character directly to input()
        self.input(char)

    def input_fkey(self, num: int, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert function key + modifier to standard control codes, then send to input()."""
        # Function key escape sequences (standard codes)
        if 1 <= num <= 4:
            # F1-F4 use ESC O P/Q/R/S format
            base_chars = {1: "P", 2: "Q", 3: "R", 4: "S"}
            if modifier == constants.KEY_MOD_NONE:
                sequence = f"{constants.ESC}O{base_chars[num]}"
            else:
                sequence = f"{constants.ESC}[1;{modifier}{base_chars[num]}"
        elif 5 <= num <= 12:
            # F5-F12 use ESC [ n ~ format
            codes = {5: 15, 6: 17, 7: 18, 8: 19, 9: 20, 10: 21, 11: 23, 12: 24}
            if modifier == constants.KEY_MOD_NONE:
                sequence = f"{constants.ESC}[{codes[num]}~"
            else:
                sequence = f"{constants.ESC}[{codes[num]};{modifier}~"
        else:
            # Unsupported function key
            return

        self.input(sequence)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to appropriate sequence based on DECNKM mode."""
        if self.numeric_keypad:
            # Numeric mode - send literal characters
            numeric_map = {
                "0": "0",
                "1": "1",
                "2": "2",
                "3": "3",
                "4": "4",
                "5": "5",
                "6": "6",
                "7": "7",
                "8": "8",
                "9": "9",
                ".": ".",
                "+": "+",
                "-": "-",
                "*": "*",
                "/": "/",
                "Enter": "\r",
            }
            sequence = numeric_map.get(key, key)
        else:
            # Application mode - send escape sequences
            application_map = {
                "0": "\x1bOp",
                "1": "\x1bOq",
                "2": "\x1bOr",
                "3": "\x1bOs",
                "4": "\x1bOt",
                "5": "\x1bOu",
                "6": "\x1bOv",
                "7": "\x1bOw",
                "8": "\x1bOx",
                "9": "\x1bOy",
                ".": "\x1bOn",
                "+": "\x1bOk",
                "-": "\x1bOm",
                "*": "\x1bOj",
                "/": "\x1bOo",
                "Enter": "\x1bOM",
            }
            sequence = application_map.get(key, key)

        self.input(sequence)

    def input(self, data: str) -> None:
        """Translate control codes based on terminal modes and send to PTY."""
        # Check if this is a cursor key sequence that needs mode translation
        if data.startswith(f"{constants.ESC}[") and len(data) == 3 and data[2] in "ABCD":
            # This is a cursor key: ESC[A, ESC[B, ESC[C, ESC[D
            if self.cursor_application_mode:
                # Convert to application mode: ESC[A -> ESC OA
                key_char = data[2]
                translated = f"{constants.ESC}O{key_char}"
                self.send(translated)
                return

        # Check if this is a function key that needs keypad mode translation
        # F1-F4 in application keypad mode might behave differently
        # For now, most function keys are the same in both modes

        # No special translation needed, send as-is
        self.send(data)

    def input_mouse(self, x: int, y: int, button: int, event_type: str, modifiers: set[str]) -> None:
        """
        Handle mouse input, cache position, and send appropriate sequence to PTY.

        Args:
            x: 1-based mouse column.
            y: 1-based mouse row.
            button: The button that was pressed/released.
            event_type: "press", "release", or "move".
            modifiers: A set of active modifiers ("shift", "meta", "ctrl").
        """
        # Cache mouse position
        self.mouse_x = x
        self.mouse_y = y

        # Determine if we should send an event based on tracking modes
        is_move = event_type == "move"
        is_press_release = event_type in ("press", "release")

        if is_move and not self.mouse_any_tracking:
            return
        if is_press_release and not self.mouse_tracking:
            return

        # SGR mode is the most common and detailed
        if self.mouse_sgr_mode:
            # Add modifier flags to the button code
            if "shift" in modifiers:
                button |= constants.MOUSE_MOD_SHIFT
            if "meta" in modifiers:
                button |= constants.MOUSE_MOD_META
            if "ctrl" in modifiers:
                button |= constants.MOUSE_MOD_CTRL

            # Determine final character ('M' for press/move, 'm' for release)
            final_char = "m" if event_type == "release" else "M"

            # For movement, the button code is special
            if is_move:
                button = constants.MOUSE_BUTTON_MOVEMENT

            mouse_seq = f"{constants.ESC}[<{button};{x};{y}{final_char}"
            self.send(mouse_seq)

    def send(self, data: str) -> None:
        """Send data to PTY without flushing (for regular input/unsolicited messages)."""
        self._send_to_pty(data, flush=False)

    def respond(self, data: str) -> None:
        """Send response to PTY with immediate flush (for query responses)."""
        self._send_to_pty(data, flush=True)

    def _send_to_pty(self, data: str, flush: bool = False) -> None:
        """Send data to PTY with optional flush."""
        if self.pty:
            self.pty.write(data)
            if flush:
                self.pty.flush()

    # Process management
    async def start_process(self) -> None:
        """Start the child process with PTY."""
        try:
            logger.info(f"Starting terminal process: {self.command}")

            # Create PTY (will be StdioPTY if stdin/stdout are provided)
            self.pty = Terminal.get_pty_handler(self.height, self.width, self.stdin, self.stdout)
            logger.info(f"Created PTY: {self.width}x{self.height}")

            # Spawn process attached to PTY
            self.process = self.pty.spawn_process(self.command)
            logger.info(f"Spawned process: pid={self.process.pid}")

            # Start async PTY reader task
            self._pty_reader_task = asyncio.create_task(self._async_read_from_pty())

        except Exception:
            logger.exception("Failed to start terminal process")
            self.stop_process()

    def stop_process(self) -> None:
        """Stop the child process and clean up."""
        if self.pty is None and self.process is None:
            return

        # Cancel PTY reader task
        if self._pty_reader_task and not self._pty_reader_task.done():
            self._pty_reader_task.cancel()
            self._pty_reader_task = None

        # Close PTY - let it handle platform-specific process cleanup
        if self.pty is not None:
            logger.info("Closing PTY")
            self.pty.close()
            self.pty = None

        self.process = None

    async def _async_read_from_pty(self) -> None:
        """Async task to read PTY data and dispatch to callback or process directly."""
        # Set PTY to non-blocking mode
        self.pty.set_nonblocking()

        while self.pty is not None and not self.pty.closed:
            try:
                # Use the PTY's async read method
                data = await self.pty.read_async(4096)

                if not data:
                    # No data available, check if process has exited
                    if self.process and self.process.poll() is not None:
                        logger.info("Process has exited, stopping terminal")
                        self.stop_process()
                        break
                    await asyncio.sleep(0.01)
                    continue

                # Use callback if set, otherwise process directly
                if self._pty_data_callback:
                    self._pty_data_callback(data)
                else:
                    self._process_pty_data_sync(data)

                # Yield control to other async operations (like resize)
                await asyncio.sleep(0)

            except asyncio.CancelledError:
                # Task was cancelled, exit cleanly
                break
            except OSError as e:
                logger.info(f"PTY read error: {e}")
                self.stop_process()
                break
            except Exception:
                logger.exception("Error reading from terminal")
                self.stop_process()
                break
