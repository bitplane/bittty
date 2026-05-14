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

from .parser import Parser
from . import constants

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

        from .devices.board import TerminalBoard

        self.board = TerminalBoard(self)

        # Process management
        self.process: Optional[subprocess.Popen] = None
        self.pty: Optional[Any] = None
        self._pty_reader_task: Optional[asyncio.Task] = None

        # PTY data callback for async handling
        self._pty_data_callback: Optional[Callable[[str], None]] = None

        # Parser
        self.parser = Parser(self, sink=self.board)

    @property
    def cursor_x(self) -> int:
        """Current cursor column."""
        return self.cursor.x

    @cursor_x.setter
    def cursor_x(self, value: int) -> None:
        self.cursor.x = value

    @property
    def cursor_y(self) -> int:
        """Current cursor row."""
        return self.cursor.y

    @cursor_y.setter
    def cursor_y(self, value: int) -> None:
        self.cursor.y = value

    @property
    def saved_cursor_x(self) -> int:
        """Saved cursor column for DECSC/DECRC compatibility."""
        return self.cursor.saved_x

    @saved_cursor_x.setter
    def saved_cursor_x(self, value: int) -> None:
        self.cursor.saved_x = value

    @property
    def saved_cursor_y(self) -> int:
        """Saved cursor row for DECSC/DECRC compatibility."""
        return self.cursor.saved_y

    @saved_cursor_y.setter
    def saved_cursor_y(self, value: int) -> None:
        self.cursor.saved_y = value

    @property
    def saved_ansi_code(self) -> str:
        """Saved ANSI style for DECSC/DECRC compatibility."""
        return self.cursor.saved_ansi_code

    @saved_ansi_code.setter
    def saved_ansi_code(self, value: str) -> None:
        self.cursor.saved_ansi_code = value

    @property
    def tab_stops(self) -> set[int]:
        """Horizontal tab stops, 0-indexed."""
        return self.cursor.tab_stops

    @tab_stops.setter
    def tab_stops(self, value: set[int]) -> None:
        self.cursor.tab_stops = value

    @property
    def primary_buffer(self):
        """Primary screen buffer."""
        return self.screen.primary_buffer

    @primary_buffer.setter
    def primary_buffer(self, value) -> None:
        self.screen.primary_buffer = value

    @property
    def alt_buffer(self):
        """Alternate screen buffer."""
        return self.screen.alt_buffer

    @alt_buffer.setter
    def alt_buffer(self, value) -> None:
        self.screen.alt_buffer = value

    @property
    def current_buffer(self):
        """Currently active screen buffer."""
        return self.screen.current_buffer

    @current_buffer.setter
    def current_buffer(self, value) -> None:
        self.screen.current_buffer = value

    @property
    def in_alt_screen(self) -> bool:
        """Whether the alternate screen buffer is active."""
        return self.screen.in_alt_screen

    @in_alt_screen.setter
    def in_alt_screen(self, value: bool) -> None:
        self.screen.in_alt_screen = value

    @property
    def scroll_top(self) -> int:
        """Top row of the active scroll region."""
        return self.screen.scroll_top

    @scroll_top.setter
    def scroll_top(self, value: int) -> None:
        self.screen.scroll_top = value

    @property
    def scroll_bottom(self) -> int:
        """Bottom row of the active scroll region."""
        return self.screen.scroll_bottom

    @scroll_bottom.setter
    def scroll_bottom(self, value: int) -> None:
        self.screen.scroll_bottom = value

    @property
    def last_printed_char(self) -> str:
        """Last printable character for REP compatibility."""
        return self.screen.last_printed_char

    @last_printed_char.setter
    def last_printed_char(self, value: str) -> None:
        self.screen.last_printed_char = value

    @property
    def g0_charset(self) -> str:
        """G0 character set designator."""
        return self.charset.g0_charset

    @g0_charset.setter
    def g0_charset(self, value: str) -> None:
        self.charset.set_g0_charset(value)

    @property
    def g1_charset(self) -> str:
        """G1 character set designator."""
        return self.charset.g1_charset

    @g1_charset.setter
    def g1_charset(self, value: str) -> None:
        self.charset.set_g1_charset(value)

    @property
    def g2_charset(self) -> str:
        """G2 character set designator."""
        return self.charset.g2_charset

    @g2_charset.setter
    def g2_charset(self, value: str) -> None:
        self.charset.set_g2_charset(value)

    @property
    def g3_charset(self) -> str:
        """G3 character set designator."""
        return self.charset.g3_charset

    @g3_charset.setter
    def g3_charset(self, value: str) -> None:
        self.charset.set_g3_charset(value)

    @property
    def current_charset(self) -> int:
        """Currently selected GL character set index."""
        return self.charset.current_charset

    @current_charset.setter
    def current_charset(self, value: int) -> None:
        self.charset.current_charset = value

    @property
    def single_shift(self) -> int | None:
        """Single-shift charset selection for the next character."""
        return self.charset.single_shift

    @single_shift.setter
    def single_shift(self, value: int | None) -> None:
        self.charset.single_shift = value

    @property
    def _charset_cache(self):
        """Charset translation cache compatibility shim."""
        return self.charset.cache

    @_charset_cache.setter
    def _charset_cache(self, value) -> None:
        self.charset.cache = value

    @property
    def _charset_array(self):
        """Precomputed charset designator array compatibility shim."""
        return self.charset.charset_array

    @_charset_array.setter
    def _charset_array(self, value) -> None:
        self.charset.charset_array = value

    @property
    def current_ansi_code(self) -> str:
        """Current ANSI style for subsequent writes."""
        return self.style.current_ansi_code

    @current_ansi_code.setter
    def current_ansi_code(self, value: str) -> None:
        self.style.current_ansi_code = value

    @property
    def title(self) -> str:
        """Window title."""
        return self.title_device.title

    @title.setter
    def title(self, value: str) -> None:
        self.title_device.title = value

    @property
    def icon_title(self) -> str:
        """Icon title."""
        return self.title_device.icon_title

    @icon_title.setter
    def icon_title(self, value: str) -> None:
        self.title_device.icon_title = value

    @property
    def mouse_x(self) -> int:
        """Last mouse column, 1-based."""
        return self.mouse.x

    @mouse_x.setter
    def mouse_x(self, value: int) -> None:
        self.mouse.x = value

    @property
    def mouse_y(self) -> int:
        """Last mouse row, 1-based."""
        return self.mouse.y

    @mouse_y.setter
    def mouse_y(self, value: int) -> None:
        self.mouse.y = value

    @property
    def show_mouse(self) -> bool:
        """Whether to render the local mouse cursor."""
        return self.mouse.show

    @show_mouse.setter
    def show_mouse(self, value: bool) -> None:
        self.mouse.show = value

    @property
    def auto_wrap(self) -> bool:
        return self.modes.auto_wrap

    @auto_wrap.setter
    def auto_wrap(self, value: bool) -> None:
        self.modes.auto_wrap = value

    @property
    def insert_mode(self) -> bool:
        return self.modes.insert_mode

    @insert_mode.setter
    def insert_mode(self, value: bool) -> None:
        self.modes.insert_mode = value

    @property
    def application_keypad(self) -> bool:
        return self.modes.application_keypad

    @application_keypad.setter
    def application_keypad(self, value: bool) -> None:
        self.modes.application_keypad = value

    @property
    def ansi_mode(self) -> bool:
        return self.modes.ansi_mode

    @ansi_mode.setter
    def ansi_mode(self, value: bool) -> None:
        self.modes.ansi_mode = value

    @property
    def cursor_application_mode(self) -> bool:
        return self.modes.cursor_application_mode

    @cursor_application_mode.setter
    def cursor_application_mode(self, value: bool) -> None:
        self.modes.cursor_application_mode = value

    @property
    def cursor_visible(self) -> bool:
        return self.modes.cursor_visible

    @cursor_visible.setter
    def cursor_visible(self, value: bool) -> None:
        self.modes.cursor_visible = value

    @property
    def cursor_blinking(self) -> bool:
        return self.modes.cursor_blinking

    @cursor_blinking.setter
    def cursor_blinking(self, value: bool) -> None:
        self.modes.cursor_blinking = value

    @property
    def scroll_mode(self) -> bool:
        return self.modes.scroll_mode

    @scroll_mode.setter
    def scroll_mode(self, value: bool) -> None:
        self.modes.scroll_mode = value

    @property
    def mouse_tracking(self) -> bool:
        return self.modes.mouse_tracking

    @mouse_tracking.setter
    def mouse_tracking(self, value: bool) -> None:
        self.modes.mouse_tracking = value

    @property
    def mouse_button_tracking(self) -> bool:
        return self.modes.mouse_button_tracking

    @mouse_button_tracking.setter
    def mouse_button_tracking(self, value: bool) -> None:
        self.modes.mouse_button_tracking = value

    @property
    def mouse_any_tracking(self) -> bool:
        return self.modes.mouse_any_tracking

    @mouse_any_tracking.setter
    def mouse_any_tracking(self, value: bool) -> None:
        self.modes.mouse_any_tracking = value

    @property
    def mouse_sgr_mode(self) -> bool:
        return self.modes.mouse_sgr_mode

    @mouse_sgr_mode.setter
    def mouse_sgr_mode(self, value: bool) -> None:
        self.modes.mouse_sgr_mode = value

    @property
    def mouse_extended_mode(self) -> bool:
        return self.modes.mouse_extended_mode

    @mouse_extended_mode.setter
    def mouse_extended_mode(self, value: bool) -> None:
        self.modes.mouse_extended_mode = value

    @property
    def urxvt_mouse(self) -> bool:
        return self.modes.urxvt_mouse

    @urxvt_mouse.setter
    def urxvt_mouse(self, value: bool) -> None:
        self.modes.urxvt_mouse = value

    @property
    def backarrow_key_sends_bs(self) -> bool:
        return self.modes.backarrow_key_sends_bs

    @backarrow_key_sends_bs.setter
    def backarrow_key_sends_bs(self, value: bool) -> None:
        self.modes.backarrow_key_sends_bs = value

    @property
    def auto_repeat(self) -> bool:
        return self.modes.auto_repeat

    @auto_repeat.setter
    def auto_repeat(self, value: bool) -> None:
        self.modes.auto_repeat = value

    @property
    def numeric_keypad(self) -> bool:
        return self.modes.numeric_keypad

    @numeric_keypad.setter
    def numeric_keypad(self, value: bool) -> None:
        self.modes.numeric_keypad = value

    @property
    def local_echo(self) -> bool:
        return self.modes.local_echo

    @local_echo.setter
    def local_echo(self, value: bool) -> None:
        self.modes.local_echo = value

    @property
    def reverse_screen(self) -> bool:
        return self.modes.reverse_screen

    @reverse_screen.setter
    def reverse_screen(self, value: bool) -> None:
        self.modes.reverse_screen = value

    @property
    def linefeed_newline_mode(self) -> bool:
        return self.modes.linefeed_newline_mode

    @linefeed_newline_mode.setter
    def linefeed_newline_mode(self, value: bool) -> None:
        self.modes.linefeed_newline_mode = value

    @property
    def origin_mode(self) -> bool:
        return self.modes.origin_mode

    @origin_mode.setter
    def origin_mode(self, value: bool) -> None:
        self.modes.origin_mode = value

    @property
    def auto_resize_mode(self) -> bool:
        return self.modes.auto_resize_mode

    @auto_resize_mode.setter
    def auto_resize_mode(self, value: bool) -> None:
        self.modes.auto_resize_mode = value

    @property
    def keyboard_usage_mode(self) -> bool:
        return self.modes.keyboard_usage_mode

    @keyboard_usage_mode.setter
    def keyboard_usage_mode(self, value: bool) -> None:
        self.modes.keyboard_usage_mode = value

    @property
    def bracketed_paste(self) -> bool:
        return self.modes.bracketed_paste

    @bracketed_paste.setter
    def bracketed_paste(self, value: bool) -> None:
        self.modes.bracketed_paste = value

    def set_pty_data_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for handling PTY data asynchronously."""
        self._pty_data_callback = callback

    def _process_pty_data_sync(self, data: str) -> None:
        """Process PTY data synchronously (fallback)."""
        self.parser.feed(data)

    def resize(self, width: int, height: int) -> None:
        """Resize terminal to new dimensions."""
        self.screen.resize(width, height)

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
        self.screen.write_text(text, ansi_code)

    def _translate_charset(self, text: str) -> str:
        """BLAZING FAST character set translation with caching! 🚀

        Optimizations:
        1. **Fast path for ASCII**: Skip translation entirely for ASCII charset
        2. **Cached charset maps**: Avoid get_charset() lookup every time
        3. **Bulk translation**: Use str.translate() for maximum speed
        4. **Pre-computed arrays**: Avoid list allocation on every call
        5. **Single-shift optimization**: Handle rare case efficiently
        """
        return self.charset.translate(text)

    def set_g0_charset(self, charset: str) -> None:
        """Set the G0 character set."""
        self.charset.set_g0_charset(charset)

    def set_g1_charset(self, charset: str) -> None:
        """Set the G1 character set."""
        self.charset.set_g1_charset(charset)

    def set_g2_charset(self, charset: str) -> None:
        """Set the G2 character set."""
        self.charset.set_g2_charset(charset)

    def set_g3_charset(self, charset: str) -> None:
        """Set the G3 character set."""
        self.charset.set_g3_charset(charset)

    def shift_in(self) -> None:
        """Shift In (SI) - switch to G0."""
        self.charset.shift_in()

    def shift_out(self) -> None:
        """Shift Out (SO) - switch to G1."""
        self.charset.shift_out()

    def single_shift_2(self) -> None:
        """Single Shift 2 (SS2) - use G2 for next character only."""
        self.charset.single_shift_2()

    def single_shift_3(self) -> None:
        """Single Shift 3 (SS3) - use G3 for next character only."""
        self.charset.single_shift_3()

    def move_cursor(self, x: Optional[int], y: Optional[int]) -> None:
        """Move cursor to position."""
        self.cursor.set_position(x, y)

    def line_feed(self, is_wrapped: bool = False) -> None:
        """Perform line feed, with optional carriage return if DECNLM is enabled."""
        self.cursor.line_feed(is_wrapped)

    def carriage_return(self) -> None:
        """Move cursor to beginning of line."""
        self.cursor.carriage_return()

    def set_tab_stop(self, x: Optional[int] = None) -> None:
        """Set a horizontal tab stop at the given column."""
        self.cursor.set_tab_stop(x)

    def next_tab_stop(self) -> int:
        """Return the next horizontal tab stop, clamped to the last column."""
        return self.cursor.next_tab_stop()

    def backspace(self) -> None:
        """Move cursor back one position."""
        self.cursor.backspace()

    def clear_screen(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear screen."""
        self.screen.clear_screen(mode)

    def clear_line(self, mode: int = constants.ERASE_FROM_CURSOR_TO_END) -> None:
        """Clear line."""
        self.screen.clear_line(mode)

    def clear_rect(self, x1: int, y1: int, x2: int, y2: int, ansi_code: str = "") -> None:
        """Clear a rectangular region."""
        self.screen.clear_rect(x1, y1, x2, y2, ansi_code)

    def alternate_screen_on(self) -> None:
        """Switch to alternate screen."""
        self.switch_screen(True)

    def alternate_screen_off(self) -> None:
        """Switch to primary screen."""
        self.switch_screen(False)

    def set_mode(self, mode: int, value: bool = True, private: bool = False) -> None:
        """Set terminal mode."""
        self.modes.set_mode(mode, value, private)

    def clear_mode(self, mode, private: bool = False) -> None:
        """Clear terminal mode."""
        self.set_mode(mode, False, private)

    def switch_screen(self, alt: bool) -> None:
        """Switch between primary and alternate screen."""
        self.screen.switch_screen(alt)

    def set_title(self, title: str) -> None:
        """Set terminal title."""
        self.title_device.set_title(title)

    def set_icon_title(self, icon_title: str) -> None:
        """Set terminal icon title."""
        self.title_device.set_icon_title(icon_title)

    def bell(self) -> None:
        """Terminal bell."""
        pass  # Subclasses can override

    def alignment_test(self) -> None:
        """Fill the screen with 'E' characters for alignment testing."""
        self.screen.alignment_test()

    def save_cursor(self) -> None:
        """Save cursor position and attributes."""
        self.cursor.save()

    def restore_cursor(self) -> None:
        """Restore cursor position and attributes."""
        self.cursor.restore()

    def set_scroll_region(self, top: int, bottom: int) -> None:
        """Set scroll region."""
        self.screen.set_scroll_region(top, bottom)

    def insert_lines(self, count: int) -> None:
        """Insert blank lines at cursor position."""
        self.screen.insert_lines(count)

    def delete_lines(self, count: int) -> None:
        """Delete lines at cursor position."""
        self.screen.delete_lines(count)

    def insert_characters(self, count: int, ansi_code: str = "") -> None:
        """Insert blank characters at cursor position."""
        self.screen.insert_characters(count, ansi_code)

    def delete_characters(self, count: int) -> None:
        """Delete characters at cursor position."""
        self.screen.delete_characters(count)

    def scroll(self, lines: int) -> None:
        """Scroll content within the active scroll region."""
        self.screen.scroll(lines)

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

        self.screen.set_column_mode(columns)

    def repeat_last_character(self, count: int) -> None:
        """Repeat the last printed character count times (REP command)."""
        self.screen.repeat_last_character(count)

    # Input handling methods
    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert key + modifier to standard control codes, then send to input()."""
        self.keyboard.input_key(char, modifier)

    def input_fkey(self, num: int, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert function key + modifier to standard control codes, then send to input()."""
        self.keyboard.input_fkey(num, modifier)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to appropriate sequence based on DECNKM mode."""
        self.keyboard.input_numpad_key(key)

    def input(self, data: str) -> None:
        """Translate control codes based on terminal modes and send to PTY."""
        self.keyboard.input(data)

    def _translate_application_cursor_keys(self, data: str) -> str:
        """Translate embedded normal cursor-key CSI sequences to application mode."""
        return self.keyboard.translate_application_cursor_keys(data)

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
        self.mouse.input_mouse(x, y, button, event_type, modifiers)

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
