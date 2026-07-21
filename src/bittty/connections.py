"""Connections and the board-side ports they plug into.

A port is a jack on the board, and both are full-duplex. The host port carries
bytes both ways (a serial line: PTY, pipe, socket). The display port carries
typed events both ways: present events down to the terminal (chrome), input
events up from it.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable, Optional, Protocol, runtime_checkable

from . import constants

if TYPE_CHECKING:
    from .caps import TerminalCaps
    from .devices.board import Board
    from .present import PresentEvent

logger = logging.getLogger(__name__)


@runtime_checkable
class Connection(Protocol):
    """A cable implementation (PTY, pipe, socket) that accepts terminal input/reply data."""

    def write(self, data: str):
        """Write data to the connected host."""


@runtime_checkable
class Presentable(Protocol):
    """A terminal (chrome) that receives discrete present events from the board."""

    def present(self, event: "PresentEvent") -> None:
        """Handle one present event."""


class HostPort:
    """The board's jack toward the child program; a Connection (PTY, pipe) plugs in.

    Full duplex: write() is the transmit pin (replies and encoded input toward
    the child); connect() starts the receive pump, feeding the child's output
    into a sink — the board wires it to its parser.
    """

    def __init__(self, connection: Connection | None = None) -> None:
        self.connection = connection
        self.on_data: Optional[Callable[[str], None]] = None
        self.on_idle: Optional[Callable[[], bool]] = None
        self.on_closed: Optional[Callable[[], None]] = None
        self._reader_task: Optional[asyncio.Task] = None

    def attach(self, connection: Connection) -> None:
        """Attach a connection to this host port (transmit side only)."""
        self.connection = connection

    def detach(self) -> None:
        """Detach the current connection."""
        self.connection = None

    def connect(
        self,
        connection: Connection,
        on_data: Callable[[str], None],
        on_idle: Optional[Callable[[], bool]] = None,
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        """Plug in a duplex connection and start pumping its receive side.

        on_data receives each decoded chunk. on_idle fires when a read returns
        nothing — return True to stop the pump (the board reaps its dead child
        there). on_closed fires when the connection errors out.
        """
        self.connection = connection
        self.on_data = on_data
        self.on_idle = on_idle
        self.on_closed = on_closed
        self._reader_task = asyncio.create_task(self._pump())

    def disconnect(self) -> None:
        """Stop the receive pump and unplug the connection."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        self._reader_task = None
        self.connection = None

    async def _pump(self) -> None:
        """Receive loop: drain the connection into on_data until it closes."""
        while self.connection is not None and not self.connection.closed:
            try:
                # A big buffer so a flooding child drains in few wakeups
                # instead of blocking on the PTY.
                data = await self.connection.read_async(65536)

                if not data:
                    if self.on_idle is not None and self.on_idle():
                        break
                    await asyncio.sleep(0.01)
                    continue

                self.on_data(data)

                # Yield control to other async operations (like resize)
                await asyncio.sleep(0)

            except asyncio.CancelledError:
                break
            except OSError as e:
                logger.info(f"Host connection read error: {e}")
                if self.on_closed is not None:
                    self.on_closed()
                break
            except Exception:
                logger.exception("Error reading from host connection")
                if self.on_closed is not None:
                    self.on_closed()
                break

    @property
    def connected(self) -> bool:
        """Whether a connection is attached."""
        return self.connection is not None

    def write(self, data: str, flush: bool = False):
        """Write data to the attached connection."""
        if self.connection is None:
            return None

        result = self.connection.write(data)
        if flush and hasattr(self.connection, "flush"):
            self.connection.flush()
        return result


class DisplayPort:
    """The board's jack toward the terminal (chrome); mirrors HostPort.

    The name is the video-connector pun, kept on purpose: the one place
    "display" survives in board vocabulary. Full duplex: the board pushes
    discrete present events down; the terminal sends input events, focus
    changes, and capability reports up. When no terminal is attached
    present() is a no-op, so the board runs headless exactly as before.
    """

    def __init__(self, board: "Board | None" = None, terminal: Presentable | None = None) -> None:
        self.board = board
        self.terminal = terminal

    def attach(self, terminal: Presentable) -> None:
        """Attach a terminal (chrome) to receive present events."""
        self.terminal = terminal

    def detach(self) -> None:
        """Detach the current terminal."""
        self.terminal = None

    @property
    def connected(self) -> bool:
        """Whether a terminal (chrome) is attached."""
        return self.terminal is not None

    def present(self, event: "PresentEvent") -> None:
        """Forward a present event to the attached terminal, if any."""
        if self.terminal is not None:
            self.terminal.present(event)

    # --- receive side: events from the terminal (chrome) --- #

    def input(self, data: str) -> None:
        """Keystrokes from the terminal, translated per keyboard modes."""
        self.board.input(data)

    def input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """A key + modifier from the terminal."""
        self.board.input_key(char, modifier)

    def input_fkey(self, num: int, modifier: int = constants.KEY_MOD_NONE) -> None:
        """A function key + modifier from the terminal."""
        self.board.input_fkey(num, modifier)

    def input_numpad_key(self, key: str) -> None:
        """A numpad key from the terminal."""
        self.board.input_numpad_key(key)

    def input_paste(self, text: str) -> None:
        """Pasted text from the terminal, bracketed per mode 2004."""
        self.board.input_paste(text)

    def input_mouse(self, x: int, y: int, button: int, event_type: str, modifiers: set[str]) -> None:
        """A mouse event from the terminal."""
        self.board.input_mouse(x, y, button, event_type, modifiers)

    def focus_in(self) -> None:
        """The box gained focus."""
        self.board.focus_in()

    def focus_out(self) -> None:
        """The box lost focus."""
        self.board.focus_out()

    def set_caps(self, caps: "TerminalCaps") -> None:
        """The terminal reports what its venue can do."""
        self.board.set_caps(caps)
