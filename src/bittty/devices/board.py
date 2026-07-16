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
        self.host = HostPort()

        self.charset = CharsetDevice(self)
        self.cursor = CursorDevice(self)
        self.keyboard = KeyboardDevice(self)
        self.modes = ModeDevice(self)
        self.mouse = MouseDevice(self)
        self.palette = PaletteDevice(self)
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
            self.modes,
            self.palette,
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
        if hard:
            self.charset.reset()

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
