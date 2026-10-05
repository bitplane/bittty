"""The board: the whole terminal emulator machine.

Hosts the devices and registers, owns the child process and its PTY, and routes
parser operations to device handlers. A terminal (chrome) (bittty.terminals) plugs into
the display port; the child program is wired to the host port via a PTY.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from threading import RLock
from typing import Any

from .. import constants
from ..caps import TerminalCaps
from ..connections import DisplayPort, HostPort
from ..keyboard.keys import KeyEvent
from ..model import DEFAULT, Model
from ..operations import Operation
from ..parser import Parser
from ..present import ChildExited, PresentEvent, ScreenChanged
from ..pty import StdioPTY, UnixPTY, WindowsPTY
from ..width import WidthPolicy
from .blitter import Blitter
from .charset import CharsetDevice
from .control import ControlDevice
from .cursor import CursorDevice
from .keyboard import KeyboardDevice
from .modes import ModeDevice
from .mouse import MouseDevice
from .palette import PaletteDevice
from .printer import PrinterDevice
from .macros import MacroDevice
from .comm import CommDevice
from .console import ConsoleDevice
from .query import QueryDevice
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
        """Create the host cable: the given streams, else a platform-appropriate PTY."""
        if stdin is not None and stdout is not None:
            return StdioPTY(stdin, stdout, rows, cols)
        if sys.platform == "win32":
            return WindowsPTY(rows, cols)
        return UnixPTY(rows, cols)

    def __init__(
        self,
        command: str = "/bin/bash",
        width: int = 80,
        height: int = 24,
        stdin=None,
        stdout=None,
        model: Model | None = None,
        palette_overrides: dict | None = None,
        width_policy: WidthPolicy | None = None,
        margin_bell_columns: int = 10,
    ) -> None:
        self.command = command
        self._output_lock = RLock()
        self.stdin = stdin
        self.stdout = stdout
        self._pty: Any | None = None
        self.process: subprocess.Popen | None = None

        self.model = model or DEFAULT
        self.palette_overrides = palette_overrides or {}
        self.conformance_level: int = 62  # DECSCL
        self.c1_eightbit: bool = False  # S7C1T/S8C1T: transmit C1 controls as 8-bit
        self.ansi_conformance_level: int = 1  # ESC SP L/M/N
        # Physical facts about the box the terminal lives in; a terminal (chrome) reports these.
        self.focused: bool = True
        self.host = HostPort(on_connected=self._host_connected)  # duplex jack toward the child
        self.display = DisplayPort(self)  # duplex jack toward the terminal (chrome)
        self.caps = TerminalCaps.unknown()  # what the real terminal can do (terminal pushes)

        self.blitter = Blitter(self, width, height, width_policy)  # first: it holds the page size the others read
        self.charset = CharsetDevice(self)
        self.cursor = CursorDevice(self)
        self.keyboard = KeyboardDevice(self)
        self.modes = ModeDevice(self)
        self.mouse = MouseDevice(self)
        self.palette = PaletteDevice(self)
        self.printer = PrinterDevice(self)
        self.comm = CommDevice(self)
        self.style = StyleDevice(self)
        self.title = TitleDevice(self)
        self.console = ConsoleDevice(self, margin_bell_columns)

        self.control = ControlDevice(self)
        self.query = QueryDevice(self)
        self.macros = MacroDevice(self)

        self.devices = {
            "charset": self.charset,
            "control": self.control,
            "cursor": self.cursor,
            "keyboard": self.keyboard,
            "modes": self.modes,
            "mouse": self.mouse,
            "palette": self.palette,
            "printer": self.printer,
            "comm": self.comm,
            "console": self.console,
            "query": self.query,
            "macros": self.macros,
            "blitter": self.blitter,
            "style": self.style,
            "title": self.title,
        }

        self.registry = self._build_registry()
        self.parser = Parser(self, feed_lock=self._output_lock)

    @property
    def width(self) -> int:
        """Columns on the page."""
        return self.blitter.width

    @property
    def height(self) -> int:
        """Lines on the page (the main display's, even while the status line is written)."""
        return self.blitter.height

    def _build_registry(self) -> dict:
        """Merge every device's operation handlers into one name -> handler table."""
        registry = {"PRINT": self._print}
        for device in self.devices.values():
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
            self.printer.emit_text(text)
            return
        self.blitter.write_text(text, self.style.current)

    def feed_host_data(self, data: bytes) -> None:
        """Canonical host-output entry point: the child's bytes, raw printer-controller data kept raw."""
        with self._output_lock:
            self.printer.feed_host_data(data, self.parser.feed)
        self.present(ScreenChanged())

    def resize(self, width: int, height: int) -> None:
        """Resize for an internal/host request, without an in-band notification."""
        if width < 1 or height < 1:
            raise ValueError("terminal dimensions must be positive")
        with self._output_lock:
            self.blitter.resize(width, height)
            if self.pty is not None:
                self.pty.resize(height, width)
        self.present(ScreenChanged())

    def resize_from_frontend(self, width: int, height: int) -> None:
        """Apply an observed outer-terminal resize, then notify an opted-in child."""
        with self._output_lock:
            self.resize(width, height)
            if self.modes.inband_resize:
                self.report_resize()

    def report_resize(self) -> None:
        """Send the mode-2048 text-area size report using known cell geometry."""
        if self.caps.cell_px is None:
            width_px = height_px = 0
        else:
            cell_width, cell_height = self.caps.cell_px
            width_px = cell_width * self.width
            height_px = cell_height * self.height
        self.host.write(
            f"{constants.ESC}[48;{self.height};{self.width};{height_px};{width_px}t",
            flush=True,
        )

    def set_page_columns(self, columns: int) -> None:
        """Apply DECSCPP and report the resulting page size to the PTY."""
        with self._output_lock:
            old_width = self.width
            self.blitter.set_page_columns(columns)
            if self.width != old_width and self.pty is not None:
                self.pty.resize(self.height, self.width)

    def present(self, event: PresentEvent) -> None:
        """Push a discrete side-effect to the attached terminal (no-op if none)."""
        self.display.present(event)

    def _host_connected(self) -> None:
        """Handle a real duplex line establishment."""
        if self.modes.auto_answerback:
            self.console.send_answerback()

    def set_caps(self, caps: TerminalCaps) -> None:
        """Record what the real terminal can do (a terminal (chrome) pushes this after probing)."""
        self.caps = caps
        if caps.grapheme_mode is not None:
            self.modes.set_grapheme_capability(caps.grapheme_mode)
        if caps.ambiguous_width is not None:
            self.blitter.detect_ambiguous_width(caps.ambiguous_width)

    def set_focus(self, focused: bool) -> None:
        """Record the box's focus state and report it to the child (DECSET 1004)."""
        self.focused = focused
        self.keyboard.report_focus(focused)

    def reset(self, hard: bool = True) -> None:
        """Reset the terminal. hard is RIS (full power-on); soft is DECSTR. Both leave the status line."""
        self.blitter.select_active_display(False)
        if hard:
            self.set_vt52(False)
        self.style.reset()
        self.modes.reset(hard=hard, reconcile=False)
        self.cursor.reset(hard=hard)
        self.blitter.reset(hard=hard)
        self.printer.reset(hard=hard)
        self.keyboard.reset(hard=hard)
        self.macros.reset(hard=hard)
        self.title.reset(hard=hard)
        self.charset.reset()
        if hard:
            self.mouse.reset()
            self.palette.reset()
        self.modes.reconcile_all()

    def set_vt52(self, on: bool) -> None:
        """Enter or leave VT52 mode (DECANM): its own parser, ASCII charsets and no autowrap.

        The ANSI charsets and DECAWM wait for the return, as in xterm 407.
        """
        if on == self.parser.vt52:
            return
        self.parser.vt52 = on
        self.modes.ansi_mode = not on
        if on:
            self._ansi_state = self.charset.save(), self.modes.auto_wrap
            self.charset.restore((0, 2, ("B", "B", "B", "B")))
            self.modes.auto_wrap = False
        else:
            charsets, self.modes.auto_wrap = self._ansi_state
            self.charset.restore(charsets)

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
        """Get current screen content as raw page data."""
        return self.blitter.main_page.get_content()

    def capture_pane(self) -> str:
        """Capture screen content: a pure pull of video memory as ANSI lines.

        No cursor or pointer is composited in — the chrome renders those from
        the board's registers (cursor.x/y, modes.cursor_visible, mouse.x/y).
        """
        page = self.blitter.main_page
        return "\n".join(page.get_line(y, width=self.width) for y in range(page.height))

    def capture_text(self, *, trim: bool = True) -> str:
        """Capture the active screen as plain text.

        By default, trailing spaces are removed from each row and unused rows
        at the bottom are omitted. Set ``trim=False`` to preserve trailing
        blank cells and rows; width-2 continuation cells emit no text.
        """
        page = self.blitter.main_page
        lines = [page.get_line_text(y) for y in range(page.height)]
        if trim:
            lines = [line.rstrip(" ") for line in lines]
            while lines and not lines[-1]:
                lines.pop()
        return "\n".join(lines)

    def capture_status_line(self) -> str:
        """The host-writable status line as plain text, trailing blanks removed."""
        return self.blitter.status_page.get_line_text(0).rstrip(" ")

    def link_at(self, x: int, y: int) -> tuple | None:
        """The hyperlink under a cell: (uri, link_id) or None.

        The chrome pulls this for hover and click arbitration — link data is
        model state; the hover effect and the click-through are chrome.
        """
        style, _ = self.blitter.current_page.get_cell(x, y)
        if style.hyperlink is None:
            return None
        return (style.hyperlink, style.hyperlink_id)

    # --- terminal wiring --- #

    def attach_display(self, display) -> None:
        """Attach a terminal (chrome) to receive present events (mirrors the host/PTY cable)."""
        self.display.attach(display)

    def detach_display(self) -> None:
        """Detach the current terminal."""
        self.display.detach()

    # --- input: thin pass-through to the input devices --- #

    def input_key_event(self, event: KeyEvent) -> None:
        """A key event with explicit identity, text and event type."""
        self.keyboard.input_key_event(event)

    def input_text(self, text: str) -> None:
        """Committed text with no physical key identity."""
        self.keyboard.input_text(text)

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
        # Raw input is safely echoable only when it is plain text/C0 data, not
        # an encoded key sequence. Typed entry points provide richer metadata.
        local_text = None if constants.ESC in data or any(0x80 <= ord(c) <= 0x9F for c in data) else data
        margin_key = bool(data) and data.isprintable()
        self.keyboard.input(data, local_text=local_text, margin_key=margin_key)

    def input_paste(self, text: str, *, phase: str = "complete") -> None:
        """Pasted text from the terminal: bracketed when mode 2004 is on, else raw.

        Bypasses keyboard translation — a paste is data, not keystrokes.
        """
        self.keyboard.input_paste(text, phase)

    def input_mouse(
        self,
        x: int,
        y: int,
        button: int,
        event_type: str,
        modifiers: set[str],
        pixel: tuple[int, int] | None = None,
    ) -> None:
        """
        Handle mouse input, cache position, and send appropriate sequence to the host.

        Args:
            x: 1-based mouse column.
            y: 1-based mouse row.
            button: The button that was pressed/released.
            event_type: "press", "release", or "move".
            modifiers: A set of active modifiers ("shift", "meta", "ctrl").
            pixel: the pointer's 0-based pixel position in the text area, if the chrome knows it.
        """
        self.mouse.input_mouse(x, y, button, event_type, modifiers, pixel)

    def focus_in(self) -> None:
        """The box gained focus: record it and report to the child if DECSET 1004 is on."""
        self.set_focus(True)

    def focus_out(self) -> None:
        """The box lost focus: record it and report to the child if DECSET 1004 is on."""
        self.set_focus(False)

    # --- process / PTY lifecycle --- #

    @property
    def pty(self) -> Any | None:
        """Attached PTY connection."""
        return self._pty

    @pty.setter
    def pty(self, value: Any | None) -> None:
        self._pty = value
        if value is None:
            self.host.detach()
        else:
            self.host.attach(value)

    def _pty_idle(self) -> bool:
        """Nothing to read this wakeup: reap the child if it has exited."""
        if self.process and self.process.poll() is not None:
            logger.info("Process has exited, stopping terminal")
            self._hang_up()
            return True
        return False

    def _hang_up(self) -> None:
        """The host side ended on its own: unplug, and tell the terminal how."""
        returncode = self.process.poll() if self.process else None
        self.stop_process()
        self.present(ChildExited(returncode))

    async def start_process(self) -> None:
        """Start the child process with PTY."""
        try:
            logger.info(f"Starting terminal process: {self.command}")

            # Create PTY (will be StdioPTY if stdin/stdout are provided)
            self.pty = Board.get_pty_handler(self.height, self.width, self.stdin, self.stdout)
            logger.info(f"Created PTY: {self.width}x{self.height}")

            # Spawn process attached to PTY (a stdio cable has none: its far end is already there)
            self.process = self.pty.spawn_process(self.command, self.pty.environment(self.model.term))
            logger.info("Spawned process: %s", self.process)

            # The host port pumps the PTY's receive side from here on
            self.host.connect(
                self.pty,
                self.feed_host_data,
                on_idle=self._pty_idle,
                on_closed=self._hang_up,
            )

        except BaseException:
            self.stop_process()  # unplug whatever was made before it failed
            raise

    def stop_process(self) -> None:
        """Stop the child process and clean up."""
        if self.pty is None and self.process is None:
            return

        self.host.disconnect()

        # Close PTY - let it handle platform-specific process cleanup
        if self.pty is not None:
            logger.info("Closing PTY")
            self.pty.close()
            self.pty = None

        self.process = None
