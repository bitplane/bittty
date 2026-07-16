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

    This class owns process/PTY lifecycle and screen capture. All terminal
    behaviour lives in the device board (`self.board`); this class is a thin
    shell over it and has no UI dependencies. Subclass it to create terminal
    widgets for specific UI frameworks.
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
        personality=None,
        palette_overrides=None,
    ) -> None:
        """Initialize terminal."""
        self.command = command
        self.width = width
        self.height = height
        self.stdin = stdin
        self.stdout = stdout
        self._pty: Optional[Any] = None

        from .devices.board import TerminalBoard

        self.board = TerminalBoard(self, personality, palette_overrides)

        # Process management
        self.process: Optional[subprocess.Popen] = None
        self._pty_reader_task: Optional[asyncio.Task] = None

        # PTY data callback for async handling
        self._pty_data_callback: Optional[Callable[[str], None]] = None

        # Parser
        self.parser = Parser(self.board)

    @property
    def personality(self):
        """The terminal personality this emulator presents to the host."""
        return self.board.personality

    @property
    def pty(self) -> Optional[Any]:
        """Attached PTY transport."""
        return self._pty

    @pty.setter
    def pty(self, value: Optional[Any]) -> None:
        self._pty = value
        if not hasattr(self, "board"):
            return
        if value is None:
            self.board.host.detach()
        else:
            self.board.host.attach(value)

    def attach_display(self, display) -> None:
        """Attach a frontend to receive present events (mirrors the host/PTY cable)."""
        self.board.display.attach(display)

    def detach_display(self) -> None:
        """Detach the current frontend."""
        self.board.display.detach()

    def set_pty_data_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for handling PTY data asynchronously."""
        self._pty_data_callback = callback

    def _process_pty_data_sync(self, data: str) -> None:
        """Process PTY data synchronously (fallback)."""
        self.parser.feed(data)

    def resize(self, width: int, height: int) -> None:
        """Resize terminal to new dimensions."""
        self.board.screen.resize(width, height)

        # Resize PTY if running
        if self.pty is not None:
            self.pty.resize(height, width)

    def get_content(self):
        """Get current screen content as raw buffer data."""
        return self.board.screen.current_buffer.get_content()

    def capture_pane(self) -> str:
        """Capture terminal content.

        The cursor cell renders only when the child wants it visible (DECTCEM)
        and the box has focus — an unfocused terminal drops its block the way a
        real one hollows it.
        """
        show_cursor = self.board.modes.cursor_visible and self.board.focused
        lines = []
        for y in range(self.height):
            lines.append(
                self.board.screen.current_buffer.get_line(
                    y,
                    width=self.width,
                    cursor_x=self.board.cursor.x,
                    cursor_y=self.board.cursor.y,
                    show_cursor=show_cursor,
                    mouse_x=self.board.mouse.x,
                    mouse_y=self.board.mouse.y,
                    show_mouse=self.board.mouse.show,
                )
            )
        return "\n".join(lines)

    def bell(self) -> None:
        """Terminal bell."""
        pass  # Subclasses can override

    # Input handling -- thin pass-through to the input devices.
    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert key + modifier to standard control codes, then send to the host."""
        self.board.keyboard.input_key(char, modifier)

    def input_fkey(self, num: int, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert function key + modifier to standard control codes, then send to the host."""
        self.board.keyboard.input_fkey(num, modifier)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to appropriate sequence based on DECNKM mode."""
        self.board.keyboard.input_numpad_key(key)

    def input(self, data: str) -> None:
        """Translate control codes based on terminal modes and send to the host."""
        self.board.keyboard.input(data)

    def focus_in(self) -> None:
        """The box gained focus: record it and report to the child if DECSET 1004 is on."""
        self.board.set_focus(True)

    def focus_out(self) -> None:
        """The box lost focus: record it and report to the child if DECSET 1004 is on."""
        self.board.set_focus(False)

    def input_mouse(self, x: int, y: int, button: int, event_type: str, modifiers: set[str]) -> None:
        """
        Handle mouse input, cache position, and send appropriate sequence to the host.

        Args:
            x: 1-based mouse column.
            y: 1-based mouse row.
            button: The button that was pressed/released.
            event_type: "press", "release", or "move".
            modifiers: A set of active modifiers ("shift", "meta", "ctrl").
        """
        self.board.mouse.input_mouse(x, y, button, event_type, modifiers)

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
                # Use the PTY's async read method (a big buffer so a flooding
                # child drains in few wakeups instead of blocking on the PTY)
                data = await self.pty.read_async(65536)

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
