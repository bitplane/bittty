"""The board: the whole terminal emulator machine.

Hosts the devices and registers, owns the child process and its PTY, and routes
parser operations to device handlers. A frontend (bittty.terminals) plugs into
the display port; the child program is wired to the host port via a PTY.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from typing import Any, Callable, Optional

from .. import constants
from ..caps import DisplayCaps
from ..operations import Operation
from ..parser import Parser
from ..personality import DEFAULT, Personality
from ..present import Bell, PresentEvent
from ..transports import DisplayPort, HostPort
from .charset import CharsetDevice
from .control import ControlDevice
from .cursor import CursorDevice
from .keyboard import KeyboardDevice
from .modes import ModeDevice
from .mouse import MouseDevice
from .palette import PaletteDevice
from .printer import PrinterDevice
from .query import QueryDevice
from .blitter import Blitter
from .style import StyleDevice
from .title import TitleDevice

logger = logging.getLogger(__name__)


class Board:
    """The terminal emulator: devices, registers, and process/PTY lifecycle."""

    @staticmethod
    def get_pty_handler(
        rows: int = constants.DEFAULT_TERMINAL_HEIGHT,
        cols: int = constants.DEFAULT_TERMINAL_WIDTH,
        stdin=None,
        stdout=None,
    ):
        """Create a platform-appropriate PTY handler."""
        if stdin is not None and stdout is not None:
            from ..pty import StdioPTY

            return StdioPTY(stdin, stdout, rows, cols)
        elif sys.platform == "win32":
            from ..pty import WindowsPTY

            return WindowsPTY(rows, cols)
        else:
            from ..pty import UnixPTY

            return UnixPTY(rows, cols)

    def __init__(
        self,
        command: str = "/bin/bash",
        width: int = 80,
        height: int = 24,
        stdin=None,
        stdout=None,
        personality: Personality | None = None,
        palette_overrides: dict | None = None,
    ) -> None:
        self.command = command
        self.width = width
        self.height = height
        self.stdin = stdin
        self.stdout = stdout
        self._pty: Optional[Any] = None
        self.process: Optional[subprocess.Popen] = None
        self._pty_reader_task: Optional[asyncio.Task] = None
        self._pty_data_callback: Optional[Callable[[str], None]] = None

        self.personality = personality or DEFAULT
        self.palette_overrides = palette_overrides or {}
        self.clipboard: dict[str, str] = {}  # OSC 52 selections; frontends sync this
        self.cwd: str = ""  # OSC 7 reported working directory
        self.pointer_shape: str = ""  # OSC 22 mouse-pointer shape
        self.font: str = ""  # OSC 50 font selection
        self.notifications: list[str] = []  # OSC 9 / 777 messages
        self.prompt_marks: list[tuple[str, int]] = []  # OSC 133 (mark, row)
        self.conformance_level: int = 62  # DECSCL
        self.c1_eightbit: bool = False  # S7C1T/S8C1T: transmit C1 controls as 8-bit
        self.ansi_conformance_level: int = 1  # ESC SP L/M/N
        # Physical facts about the box the terminal lives in; a frontend reports these.
        self.focused: bool = True
        # XTWINOPS window state; a windowing frontend actuates these.
        self.window_iconified: bool = False
        self.window_maximized: bool = False
        self.window_fullscreen: bool = False
        self.window_position: tuple[int, int] = (0, 0)
        self.window_requests: list[str] = []  # "raise" / "lower" / "refresh"
        # linux console setterm hardware registers; a display/audio backend actuates these.
        self.screen_blanked: bool = False
        self.blank_timeout: int = 0  # minutes; 0 = never
        self.bell_hz: int = 750
        self.bell_ms: int = 125
        self.vesa_powerdown: int = 0
        self.cursor_blink_ms: int = 0
        self.default_underline_color: int | None = None
        self.default_dim_color: int | None = None
        self.console_requests: list[tuple[str, int]] = []  # ("switch", n) / ("previous", 0)
        self.answerback: str = ""  # ENQ reply string; a frontend/config sets it
        self.warning_bell_volume: int = 8  # DECSWBV (0-8)
        self.margin_bell_volume: int = 0  # DECSMBV (0-8)
        self.host = HostPort()  # board -> child (replies, encoded input)
        self.display = DisplayPort()  # board -> frontend (present events)
        self.display_caps = DisplayCaps.unknown()  # what the real terminal can do (frontend pushes)

        self.charset = CharsetDevice(self)
        self.cursor = CursorDevice(self)
        self.keyboard = KeyboardDevice(self)
        self.modes = ModeDevice(self)
        self.mouse = MouseDevice(self)
        self.palette = PaletteDevice(self)
        self.printer = PrinterDevice(self)
        self.blitter = Blitter(self)
        self.style = StyleDevice(self)
        self.title = TitleDevice(self)

        self.control = ControlDevice(self)
        self.query = QueryDevice(self)

        self.devices = {
            "charset": self.charset,
            "control": self.control,
            "cursor": self.cursor,
            "host": self.host,
            "keyboard": self.keyboard,
            "modes": self.modes,
            "mouse": self.mouse,
            "palette": self.palette,
            "printer": self.printer,
            "query": self.query,
            "blitter": self.blitter,
            "style": self.style,
            "title": self.title,
        }

        self.registry = self._build_registry()
        self.parser = Parser(self)

    @property
    def board(self) -> "Board":
        """Compat shim: pre-dissolve code reached the board via `.board`. Remove next release."""
        return self

    def _build_registry(self) -> dict:
        """Merge every device's operation handlers into one name -> handler table."""
        registry = {"PRINT": self._print}
        for device in (
            self.charset,
            self.control,
            self.cursor,
            self.keyboard,
            self.modes,
            self.mouse,
            self.palette,
            self.printer,
            self.blitter,
            self.style,
            self.query,
            self.title,
        ):
            for name, handler in device.handlers.items():
                if name in registry:
                    raise ValueError(f"operation {name!r} claimed by more than one device")
                registry[name] = handler
        return registry

    def _print(self, operation: Operation) -> None:
        self.print_text(operation.args[0])

    def print_text(self, text: str) -> None:
        """Write printable text (the parser's fast path — no Operation wrapper)."""
        if self.printer.controller_mode:  # MC printer-controller: text goes to paper, not the screen
            self.printer.emit(text)
            return
        self.blitter.write_text(text, self.style.current)

    def resize(self, width: int, height: int) -> None:
        """Resize the terminal, including buffers and the attached PTY."""
        self.blitter.resize(width, height)
        if self.pty is not None:
            self.pty.resize(height, width)

    def bell(self) -> None:
        """Ring the terminal bell: pushed to the frontend as a present event."""
        self.present(Bell())

    def present(self, event: PresentEvent) -> None:
        """Push a discrete side-effect to the attached frontend (no-op if none)."""
        self.display.present(event)

    def set_display_caps(self, caps: DisplayCaps) -> None:
        """Record what the real terminal can do (a frontend pushes this after probing)."""
        self.display_caps = caps

    def set_focus(self, focused: bool) -> None:
        """Record the box's focus state and report it to the child (DECSET 1004)."""
        self.focused = focused
        self.keyboard.report_focus(focused)

    def reset(self, hard: bool = True) -> None:
        """Reset the terminal. hard is RIS (full power-on); soft is DECSTR."""
        self.style.reset()
        self.modes.reset(hard=hard)
        self.cursor.reset(hard=hard)
        self.blitter.reset(hard=hard)
        self.printer.reset(hard=hard)
        self.keyboard.reset(hard=hard)
        if hard:
            self.charset.reset()
            self.palette.reset()

    def get_device(self, name: str):
        """Return a plugged-in device by slot name."""
        return self.devices[name]

    def handle_operation(self, operation: Operation) -> None:
        handler = self.registry.get(operation.name)
        if handler is not None:
            handler(operation)
            return
        logger.debug("Unhandled operation: %s", operation)

    # --- screen capture --- #

    def get_content(self):
        """Get current screen content as raw buffer data."""
        return self.blitter.current_buffer.get_content()

    def capture_pane(self) -> str:
        """Capture terminal content.

        The cursor cell renders only when the child wants it visible (DECTCEM)
        and the box has focus — an unfocused terminal drops its block the way a
        real one hollows it.
        """
        show_cursor = self.modes.cursor_visible and self.focused
        lines = []
        for y in range(self.height):
            lines.append(
                self.blitter.current_buffer.get_line(
                    y,
                    width=self.width,
                    cursor_x=self.cursor.x,
                    cursor_y=self.cursor.y,
                    show_cursor=show_cursor,
                    mouse_x=self.mouse.x,
                    mouse_y=self.mouse.y,
                    show_mouse=self.mouse.show,
                )
            )
        return "\n".join(lines)

    # --- frontend wiring --- #

    def attach_display(self, display) -> None:
        """Attach a frontend to receive present events (mirrors the host/PTY cable)."""
        self.display.attach(display)

    def detach_display(self) -> None:
        """Detach the current frontend."""
        self.display.detach()

    # --- input: thin pass-through to the input devices --- #

    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert key + modifier to standard control codes, then send to the host."""
        self.keyboard.input_key(char, modifier)

    def input_fkey(self, num: int, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Convert function key + modifier to standard control codes, then send to the host."""
        self.keyboard.input_fkey(num, modifier)

    def input_numpad_key(self, key: str) -> None:
        """Convert numpad key to appropriate sequence based on DECNKM mode."""
        self.keyboard.input_numpad_key(key)

    def input(self, data: str) -> None:
        """Translate control codes based on terminal modes and send to the host."""
        self.keyboard.input(data)

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
        self.mouse.input_mouse(x, y, button, event_type, modifiers)

    def focus_in(self) -> None:
        """The box gained focus: record it and report to the child if DECSET 1004 is on."""
        self.set_focus(True)

    def focus_out(self) -> None:
        """The box lost focus: record it and report to the child if DECSET 1004 is on."""
        self.set_focus(False)

    # --- process / PTY lifecycle --- #

    @property
    def pty(self) -> Optional[Any]:
        """Attached PTY connection."""
        return self._pty

    @pty.setter
    def pty(self, value: Optional[Any]) -> None:
        self._pty = value
        if value is None:
            self.host.detach()
        else:
            self.host.attach(value)

    def set_pty_data_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for handling PTY data asynchronously."""
        self._pty_data_callback = callback

    def _process_pty_data_sync(self, data: str) -> None:
        """Process PTY data synchronously (fallback)."""
        self.parser.feed(data)

    async def start_process(self) -> None:
        """Start the child process with PTY."""
        try:
            logger.info(f"Starting terminal process: {self.command}")

            # Create PTY (will be StdioPTY if stdin/stdout are provided)
            self.pty = Board.get_pty_handler(self.height, self.width, self.stdin, self.stdout)
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
