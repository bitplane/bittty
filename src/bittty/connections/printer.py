"""The printer port, and the protocol a cable to the auxiliary printer implements."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import IntEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .printer_config import PrinterConfiguration

logger = logging.getLogger(__name__)


class PrinterStatus(IntEnum):
    """DEC printer-status values returned by DSR (CSI ? 15 n)."""

    READY = 10
    NOT_READY = 11
    OFFLINE = 13
    BUSY = 18
    ASSIGNED = 19


@runtime_checkable
class PrinterConnection(Protocol):
    """A byte-oriented cable plugged into the terminal's printer port."""

    closed: bool
    status: PrinterStatus

    def write_bytes(self, data: bytes) -> int:
        """Send bytes from the terminal to the printer."""

    def flush(self) -> None:
        """Push anything buffered toward the printer."""

    async def read_bytes_async(self, size: int) -> bytes:
        """The printer's next bytes toward the host; empty when there are none yet."""

    def configure(self, configuration: PrinterConfiguration) -> None:
        """Apply a configuration snapshot; a cable with no adapter to set has nothing to apply."""


class PrinterPort:
    """The board's byte-oriented, full-duplex auxiliary-printer jack.

    What is on the far end is outside the terminal, so its failures are caught
    here: a jammed printer reports NOT_READY instead of damaging terminal state.
    """

    def __init__(
        self,
        connection: PrinterConnection | None = None,
        on_data: Callable[[bytes], None] | None = None,
    ) -> None:
        self.connection = connection
        self.on_data = on_data
        self._reader_task: asyncio.Task | None = None
        self._failed = False

    def attach(self, connection: PrinterConnection) -> None:
        """Attach a transmit-only connection without starting a read pump."""
        self.disconnect()
        self.connection = connection
        self._failed = False

    def connect(self, connection: PrinterConnection) -> None:
        """Attach a connection and pump its receive side."""
        self.attach(connection)
        self._reader_task = asyncio.create_task(self._pump())

    def disconnect(self) -> None:
        """Stop inbound reads and detach the printer cable."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        self._reader_task = None
        self.connection = None

    @property
    def connected(self) -> bool:
        return self.connection is not None

    @property
    def status(self) -> PrinterStatus:
        """The connection's reported status, NOT_READY once it has failed, OFFLINE with none."""
        if self.connection is None:
            return PrinterStatus.OFFLINE
        if self._failed:
            return PrinterStatus.NOT_READY
        return self.connection.status

    def write_bytes(self, data: bytes, *, flush: bool = False):
        """Send bytes to the printer; connection failures do not damage terminal state."""
        if self.connection is None:
            return None
        try:
            result = self.connection.write_bytes(data)
            if flush:
                self.connection.flush()
            return result
        except Exception:
            self._failed = True
            logger.info("Printer connection write failed", exc_info=True)
            return None

    def configure(self, configuration: PrinterConfiguration) -> None:
        """Offer a complete configuration snapshot to the connection."""
        if self.connection is None:
            return
        try:
            self.connection.configure(configuration)
            self._failed = False
        except Exception:
            self._failed = True
            logger.info("Printer connection configuration failed", exc_info=True)

    async def _pump(self) -> None:
        connection = self.connection
        while self.connection is connection and not connection.closed:
            try:
                data = await connection.read_bytes_async(65536)
                if not data:
                    await asyncio.sleep(0.01)
                    continue
                if self.on_data is not None:
                    self.on_data(data)
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                break
            except (OSError, ValueError):
                self._failed = True
                logger.info("Printer connection read failed", exc_info=True)
                break
            except Exception:
                self._failed = True
                logger.exception("Error reading from printer connection")
                break
