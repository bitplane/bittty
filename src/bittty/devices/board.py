"""Terminal device board/backplane."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..operations import Operation
from ..personality import DEFAULT, Personality
from ..transports import HostPort
from .charset import CharsetDevice
from .control import ControlDevice
from .cursor import CursorDevice
from .keyboard import KeyboardDevice
from .modes import ModeDevice
from .mouse import MouseDevice
from .palette import PaletteDevice
from .printer import PrinterDevice
from .query import QueryDevice
from .screen import ScreenDevice
from .style import StyleDevice
from .title import TitleDevice

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


class TerminalBoard:
    """Hosts terminal devices and routes parser operations to them."""

    def __init__(
        self,
        terminal: Terminal,
        personality: Personality | None = None,
        palette_overrides: dict | None = None,
    ) -> None:
        self.terminal = terminal
        self.personality = personality or DEFAULT
        self.palette_overrides = palette_overrides or {}
        self.clipboard: dict[str, str] = {}  # OSC 52 selections; frontends sync this
        self.cwd: str = ""  # OSC 7 reported working directory
        self.notifications: list[str] = []  # OSC 9 / 777 messages
        self.prompt_marks: list[tuple[str, int]] = []  # OSC 133 (mark, row)
        self.conformance_level: int = 62  # DECSCL
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
        self.host = HostPort()

        self.charset = CharsetDevice(self)
        self.cursor = CursorDevice(self)
        self.keyboard = KeyboardDevice(self)
        self.modes = ModeDevice(self)
        self.mouse = MouseDevice(self)
        self.palette = PaletteDevice(self)
        self.printer = PrinterDevice(self)
        self.screen = ScreenDevice(self)
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
            "screen": self.screen,
            "style": self.style,
            "title": self.title,
        }

        self.registry = self._build_registry()

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
            self.screen,
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
        if self.printer.controller_mode:  # MC printer-controller: text goes to paper, not the screen
            self.printer.emit(operation.args[0])
            return
        self.screen.write_text(operation.args[0], self.style.current)

    def resize(self, width: int, height: int) -> None:
        """Resize the terminal, including buffers and the attached PTY."""
        self.terminal.resize(width, height)

    def bell(self) -> None:
        """Ring the terminal bell (UI hook, overridable on the Terminal)."""
        self.terminal.bell()

    def reset(self, hard: bool = True) -> None:
        """Reset the terminal. hard is RIS (full power-on); soft is DECSTR."""
        self.style.reset()
        self.modes.reset(hard=hard)
        self.cursor.reset(hard=hard)
        self.screen.reset(hard=hard)
        self.printer.reset(hard=hard)
        if hard:
            self.charset.reset()
            self.palette.reset()

    @property
    def width(self) -> int:
        """Terminal width in columns."""
        return self.terminal.width

    @width.setter
    def width(self, value: int) -> None:
        self.terminal.width = value

    @property
    def height(self) -> int:
        """Terminal height in rows."""
        return self.terminal.height

    @height.setter
    def height(self, value: int) -> None:
        self.terminal.height = value

    def get_device(self, name: str):
        """Return a plugged-in device by slot name."""
        return self.devices[name]

    def handle_operation(self, operation: Operation) -> None:
        handler = self.registry.get(operation.name)
        if handler is not None:
            handler(operation)
            return
        logger.debug("Unhandled operation: %s", operation)
