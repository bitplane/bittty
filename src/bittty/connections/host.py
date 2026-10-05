"""The host port, and the protocol a cable to the child program implements."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .serial_line import SerialLine

logger = logging.getLogger(__name__)


@runtime_checkable
class Connection(Protocol):
    """A host cable (PTY, pipe, socket): text and protocol bytes out to the host, bytes back."""

    closed: bool

    def write(self, data: str) -> int:
        """Send text to the host."""

    def write_bytes(self, data: bytes) -> int:
        """Send protocol bytes to the host, unencoded."""

    def flush(self) -> None:
        """Push anything buffered toward the host."""

    async def read_bytes_async(self, size: int) -> bytes:
        """The host's next output; empty when there is none yet."""

    def configure_line(self, line: SerialLine) -> None:
        """Apply the host line's settings; a cable with no modem (a PTY) has nothing to apply."""

    def resize(self, rows: int, cols: int) -> None:
        """Tell the far end the screen's new size."""

    def close(self) -> None:
        """Unplug the cable."""


class HostPort:
    """The board's jack toward the child program; a Connection (PTY, pipe) plugs in.

    Full duplex: write() is the transmit pin (replies and encoded input toward
    the child); connect() starts the receive pump, feeding the child's output
    into a sink — the board wires it to its parser.
    """

    def __init__(
        self,
        connection: Connection | None = None,
        on_connected: Callable[[], None] | None = None,
    ) -> None:
        self.connection = connection
        self.on_connected = on_connected
        self.on_data: Callable[[bytes], None] | None = None
        self.on_idle: Callable[[], bool] | None = None
        self.on_closed: Callable[[], None] | None = None
        self._reader_task: asyncio.Task | None = None
        self.line: SerialLine | None = None  # the host line's settings, on a terminal that has them

    def attach(self, connection: Connection) -> None:
        """Attach a connection to this host port (transmit side only)."""
        self.connection = connection
        self._offer_line()

    def configure(self, line: SerialLine) -> None:
        """Hold the host line's settings and offer them to the connection."""
        self.line = line
        self._offer_line()

    def _offer_line(self) -> None:
        if self.line is not None and self.connection is not None:
            self.connection.configure_line(self.line)

    def detach(self) -> None:
        """Detach the current connection."""
        self.connection = None

    def connect(
        self,
        connection: Connection,
        on_data: Callable[[bytes], None],
        on_idle: Callable[[], bool] | None = None,
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        """Plug in a duplex connection and start pumping its receive side.

        on_data receives each chunk of bytes. on_idle fires when a read returns
        nothing — return True to stop the pump (the board reaps its dead child
        there). on_closed fires when the connection closes or errors out.
        """
        self.connection = connection
        self.on_data = on_data
        self.on_idle = on_idle
        self.on_closed = on_closed
        if self.on_connected is not None:
            self.on_connected()
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
                data = await self.connection.read_bytes_async(65536)

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
        else:
            # The cable reported itself closed (end of a stream, a dropped socket).
            if self.connection is not None and self.on_closed is not None:
                self.on_closed()

    @property
    def connected(self) -> bool:
        """Whether a connection is attached."""
        return self.connection is not None

    def write(self, data: str, flush: bool = False):
        """Write data to the attached connection."""
        if self.connection is None:
            return None
        result = self.connection.write(data)
        if flush:
            self.connection.flush()
        return result

    def write_bytes(self, data: bytes, flush: bool = False):
        """Write protocol bytes without passing them through UTF-8 encoding."""
        if self.connection is None:
            return None
        result = self.connection.write_bytes(data)
        if flush:
            self.connection.flush()
        return result
