"""The board: the whole terminal emulator machine.

Hosts the devices and registers, owns the child process and its PTY, and routes
parser operations to device handlers. A terminal (chrome) (bittty.terminals) plugs into
the display port; the child program is wired to the host port via a PTY.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any, Callable

from .. import constants
from ..caps import TerminalCaps
from ..operations import Operation
from ..parser import Parser
from ..model import DEFAULT, Model
from ..present import Bell, PresentEvent
from ..connections import DisplayPort, HostPort
from ..width import DEFAULT_WIDTH_POLICY, WidthPolicy
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
        model: Model | None = None,
        palette_overrides: dict | None = None,
        width_policy: WidthPolicy | None = None,
    ) -> None:
        self.command = command
        self.width = width
        self.height = height
        self.stdin = stdin
        self.stdout = stdout
        self._pty: Any | None = None
        self.process: subprocess.Popen | None = None
        self._pty_data_callback: Callable[[str], None] | None = None

        self.model = model or DEFAULT
        self.palette_overrides = palette_overrides or {}
        self._width_policy_explicit = width_policy is not None
        self._width_policy_baseline = width_policy or DEFAULT_WIDTH_POLICY
        self._width_policy_overridden = False
        self.width_policy = self._width_policy_baseline
        self.clipboard: dict[str, str] = {}  # OSC 52 selections; terminals sync this
        self.cwd: str = ""  # OSC 7 reported working directory
        self.pointer_shape: str = ""  # OSC 22 mouse-pointer shape
        self.font: str = ""  # OSC 50 font selection
        self.notifications: list[str] = []  # OSC 9 / 777 messages
        self.prompt_marks: list[tuple[str, int]] = []  # OSC 133 (mark, row)
        self.conformance_level: int = 62  # DECSCL
        self.c1_eightbit: bool = False  # S7C1T/S8C1T: transmit C1 controls as 8-bit
        self.ansi_conformance_level: int = 1  # ESC SP L/M/N
        # Physical facts about the box the terminal lives in; a terminal (chrome) reports these.
        self.focused: bool = True
        # XTWINOPS window state; a windowing terminal actuates these.
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
        self.answerback: str = ""  # ENQ reply string; the chrome or config sets it
        self.warning_bell_volume: int = 8  # DECSWBV (0-8)
        self.margin_bell_volume: int = 0  # DECSMBV (0-8)
        self.host = HostPort()  # duplex jack toward the child (PTY plugs in)
        self.display = DisplayPort(self)  # duplex jack toward the terminal (chrome)
        self.caps = TerminalCaps.unknown()  # what the real terminal can do (terminal pushes)

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

    def set_page_columns(self, columns: int) -> None:
        """Apply DECSCPP and report the resulting page size to the PTY."""
        old_width = self.width
        self.blitter.set_page_columns(columns)
        if self.width != old_width and self.pty is not None:
            self.pty.resize(self.height, self.width)

    def bell(self) -> None:
        """Ring the terminal bell: pushed to the terminal (chrome) as a present event."""
        self.present(Bell())

    def present(self, event: PresentEvent) -> None:
        """Push a discrete side-effect to the attached terminal (no-op if none)."""
        self.display.present(event)

    def set_caps(self, caps: TerminalCaps) -> None:
        """Record what the real terminal can do (a terminal (chrome) pushes this after probing)."""
        self.caps = caps
        if caps.grapheme_mode is not None:
            self.modes.set_grapheme_capability(caps.grapheme_mode)
        if not self._width_policy_explicit and caps.ambiguous_width is not None:
            self._width_policy_baseline = WidthPolicy(ambiguous_width=caps.ambiguous_width)
            if not self._width_policy_overridden:
                self._install_width_policy(self._width_policy_baseline)
                self.modes.ambiguous_width_double = caps.ambiguous_width == 2

    def _install_width_policy(self, policy: WidthPolicy) -> None:
        """Make a policy active for future writes on both video pages."""
        self.width_policy = policy
        self.blitter.set_width_policy(policy)

    def set_ambiguous_width(self, width: int, *, mode_override: bool = True) -> None:
        """Set the active ambiguous width without reinterpreting stored cells."""
        if mode_override:
            self._width_policy_overridden = True
        self._install_width_policy(WidthPolicy(ambiguous_width=width))
        self.modes.ambiguous_width_double = width == 2

    def restore_width_policy(self) -> None:
        """Clear a runtime override and restore the constructor/detected baseline."""
        self._width_policy_overridden = False
        self._install_width_policy(self._width_policy_baseline)
        self.modes.ambiguous_width_double = self._width_policy_baseline.ambiguous_width == 2

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
        """Capture screen content: a pure pull of video memory as ANSI lines.

        No cursor or pointer is composited in — the chrome renders those from
        the board's registers (cursor.x/y, modes.cursor_visible, mouse.x/y).
        """
        page = self.blitter.current_buffer
        return "\n".join(page.get_line(y, width=self.width) for y in range(self.height))

    def capture_text(self, *, trim: bool = True) -> str:
        """Capture the active screen as plain text.

        By default, trailing spaces are removed from each row and unused rows
        at the bottom are omitted. Set ``trim=False`` to preserve trailing
        blank cells and rows; width-2 continuation cells emit no text.
        """
        page = self.blitter.current_buffer
        lines = [page.get_line_text(y) for y in range(self.height)]
        if trim:
            lines = [line.rstrip(" ") for line in lines]
            while lines and not lines[-1]:
                lines.pop()
        return "\n".join(lines)

    def link_at(self, x: int, y: int) -> tuple | None:
        """The hyperlink under a cell: (uri, link_id) or None.

        The chrome pulls this for hover and click arbitration — link data is
        model state; the hover effect and the click-through are chrome.
        """
        style, _ = self.blitter.current_buffer.get_cell(x, y)
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

    def input_paste(self, text: str) -> None:
        """Pasted text from the terminal: bracketed when mode 2004 is on, else raw.

        Bypasses keyboard translation — a paste is data, not keystrokes.
        """
        if self.modes.bracketed_paste:
            self.host.write(f"\x1b[200~{text}\x1b[201~")
        else:
            self.host.write(text)

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

    def set_pty_data_callback(self, callback: Callable[[str], None]) -> None:
        """Swap the host port's receive sink (a terminal uses this to add render throttling)."""
        self._pty_data_callback = callback

    def _dispatch_pty_data(self, data: str) -> None:
        """The host port's receive sink: the callback if set, else straight into the parser."""
        (self._pty_data_callback or self.parser.feed)(data)

    def _pty_idle(self) -> bool:
        """Nothing to read this wakeup: reap the child if it has exited."""
        if self.process and self.process.poll() is not None:
            logger.info("Process has exited, stopping terminal")
            self.stop_process()
            return True
        return False

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

            # The host port pumps the PTY's receive side from here on
            self.host.connect(
                self.pty,
                self._dispatch_pty_data,
                on_idle=self._pty_idle,
                on_closed=self.stop_process,
            )

        except Exception:
            logger.exception("Failed to start terminal process")
            self.stop_process()

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
