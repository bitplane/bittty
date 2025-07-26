"""
Terminal: Base terminal emulator class.

This module provides the core Terminal class that manages terminal state,
process control, and screen buffers. UI frameworks can subclass this to
create terminal widgets.
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

logger = logging.getLogger(__name__)


class Terminal:
    """
    Base terminal emulator with process management and screen buffers.

    This class handles all terminal logic but has no UI dependencies.
    Subclass this to create terminal widgets for specific UI frameworks.
    """

    @staticmethod
    def get_pty_handler(rows: int = constants.DEFAULT_TERMINAL_HEIGHT, cols: int = constants.DEFAULT_TERMINAL_WIDTH):
        """Create a platform-appropriate PTY handler.

        Args:
            rows: Terminal height in characters
            cols: Terminal width in characters

        Returns:
            PTY handler object with read/write/resize interface
        """
        if sys.platform == "win32":
            from .pty_windows import WindowsPTY

            return WindowsPTY(rows, cols)
        else:
            from .pty_unix import UnixPTY

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
        self.mouse_tracking = False
        self.mouse_button_tracking = False
        self.mouse_any_tracking = False
        self.mouse_sgr_mode = False
        self.mouse_extended_mode = False

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
        """Capture terminal content like tmux capture-pane."""
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

        # Insert or overwrite based on mode
        if self.insert_mode:
            self.current_buffer.insert(self.cursor_x, self.cursor_y, text, code_to_use)
        else:
            self.current_buffer.set(self.cursor_x, self.cursor_y, text, code_to_use)

        # Move cursor forward by character count
        if self.auto_wrap or self.cursor_x < self.width - 1:
            self.cursor_x += len(text)

        # Remember last character for REP command
        if text:
            self.last_printed_char = text[-1]

    def move_cursor(self, x: Optional[int], y: Optional[int]) -> None:
        """Move cursor to position."""
        if x is not None:
            self.cursor_x = max(0, min(x, self.width - 1))
        if y is not None:
            self.cursor_y = max(0, min(y, self.height - 1))

    def line_feed(self, is_wrapped: bool = False) -> None:
        """Perform line feed."""
        if self.cursor_y >= self.scroll_bottom:
            # Scroll up within scroll region
            self.scroll_up(1)
        else:
            # Move cursor down
            self.cursor_y += 1

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

    def scroll_up(self, count: int) -> None:
        """Scroll content up within scroll region."""
        # Only scroll within the defined scroll region
        for _ in range(count):
            if self.scroll_top < self.scroll_bottom:
                # Shift lines up within the scroll region
                for y in range(self.scroll_top, self.scroll_bottom):
                    for x in range(self.width):
                        cell = self.current_buffer.get_cell(x, y + 1)
                        self.current_buffer.set_cell(x, y, cell[1], cell[0])
                # Clear the last line of the scroll region
                self.current_buffer.clear_line(self.scroll_bottom, constants.ERASE_ALL)
            else:
                # If scroll region is 1 line or invalid, just clear it
                self.current_buffer.clear_line(self.scroll_top, constants.ERASE_ALL)

    def scroll_down(self, count: int) -> None:
        """Scroll content down within scroll region."""
        # Only scroll within the defined scroll region
        for _ in range(count):
            if self.scroll_top < self.scroll_bottom:
                # Shift lines down within the scroll region
                for y in range(self.scroll_bottom, self.scroll_top, -1):
                    for x in range(self.width):
                        cell = self.current_buffer.get_cell(x, y - 1)
                        self.current_buffer.set_cell(x, y, cell[1], cell[0])
                # Clear the first line of the scroll region
                self.current_buffer.clear_line(self.scroll_top, constants.ERASE_ALL)
            else:
                # If scroll region is 1 line or invalid, just clear it
                self.current_buffer.clear_line(self.scroll_top, constants.ERASE_ALL)

    def set_cursor(self, x: Optional[int], y: Optional[int]) -> None:
        """Set cursor position (alias for move_cursor)."""
        self.move_cursor(x, y)

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

    def input(self, data: str) -> None:
        """Translate control codes based on terminal modes and send to PTY."""
        # Check if this is a cursor key sequence that needs mode translation
        if data.startswith(f"{constants.ESC}[") and len(data) == 3 and data[2] in "ABCD":
            # This is a cursor key: ESC[A, ESC[B, ESC[C, ESC[D
            if self.cursor_application_mode:
                # Convert to application mode: ESC[A -> ESC OA
                key_char = data[2]
                translated = f"{constants.ESC}O{key_char}"
                self._send_to_pty(translated)
                return

        # Check if this is a function key that needs keypad mode translation
        # F1-F4 in application keypad mode might behave differently
        # For now, most function keys are the same in both modes

        # No special translation needed, send as-is
        self._send_to_pty(data)

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
            self._send_to_pty(mouse_seq)

    def _send_to_pty(self, data: str) -> None:
        """Send data to PTY or stdout."""
        if self.pty:
            # PTY mode
            self.pty.write(data)
        elif self.stdout:
            # Stream mode
            self.stdout.write(data)
            self.stdout.flush()

    # Process management
    async def start_process(self) -> None:
        """Start the child process with PTY or set up stream mode."""
        try:
            if self.stdin is not None and self.stdout is not None:
                # Stream mode - create PTY for child process but also read from stdin
                logger.info("Starting terminal in stream mode")

                # Create PTY and spawn child process (for output)
                self.pty = Terminal.get_pty_handler(self.height, self.width)
                logger.info(f"Created PTY: {self.width}x{self.height}")
                self.process = self.pty.spawn_process(self.command)
                logger.info(f"Spawned process: pid={self.process.pid}")

                # Start both PTY reader (for child output) and stdin reader (for input)
                self._pty_reader_task = asyncio.create_task(self._async_read_from_pty())
                self._stdin_reader_task = asyncio.create_task(self._async_read_from_stdin())
            else:
                # PTY mode - create child process
                logger.info(f"Starting terminal process: {self.command}")

                # Create PTY socket
                self.pty = Terminal.get_pty_handler(self.height, self.width)
                logger.info(f"Created PTY: {self.width}x{self.height}")

                # Spawn process attached to PTY
                self.process = self.pty.spawn_process(self.command)
                logger.info(f"Spawned process: pid={self.process.pid}")

                # Start async PTY reader task
                self._pty_reader_task = asyncio.create_task(self._async_read_from_pty())

        except Exception:
            logger.exception("Failed to start terminal process")
            self.stop_process()

    async def _async_read_from_stdin(self) -> None:
        """Async task to read from stdin in stream mode."""
        loop = asyncio.get_running_loop()

        def read_stdin():
            try:
                # Read available data from stdin
                import os

                data = os.read(self.stdin.fileno(), 1024)
                return data.decode("utf-8", errors="replace")
            except (OSError, IOError):
                return ""

        try:
            while True:
                # Read from stdin in a thread to avoid blocking
                data = await loop.run_in_executor(None, read_stdin)
                if not data:
                    await asyncio.sleep(0.01)  # Small delay if no data
                    continue

                # Forward input directly to PTY - parser is for output parsing only
                try:
                    if self.pty:
                        self.pty.write(data)
                except UnicodeDecodeError:
                    pass

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Error reading from stdin: {e}")

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
