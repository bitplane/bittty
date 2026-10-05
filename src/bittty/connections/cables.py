"""Cables whose far end is memory or a stream, rather than a process or a device.

MemoryConnection is the host-side test cable. MemoryPrinter and StreamPrinter are
printer cables, not printers: the thing that simulates a printer is
bittty.peripherals.printer.VirtualPrinter.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, BinaryIO

from .printer import PrinterStatus

if TYPE_CHECKING:
    from .printer_config import PrinterConfiguration
    from .serial_line import SerialLine


class MemoryConnection:
    """A Connection whose far end is memory, not a process.

    The host-port sibling of MemoryPrinter: it records everything the board
    transmits and can feed data back as if a child had produced it. Real enough
    to test against — a board wired to one behaves exactly as it does on a PTY,
    which is why the suite uses it instead of standing a mock in for the cable.
    """

    def __init__(self, receive=()) -> None:
        self.data: list = []  # every write, in order, as it was given
        self.flush_count = 0
        self.closed = False
        self.resizes: list[tuple[int, int]] = []
        self.lines: list[SerialLine] = []  # each host line configuration offered, in order
        self._inbound = list(receive)

    @property
    def text(self) -> str:
        """Everything transmitted so far, joined."""
        return "".join(part if isinstance(part, str) else part.decode("latin-1") for part in self.data)

    def write(self, data: str) -> int:
        self.data.append(data)
        return len(data)

    def write_bytes(self, data: bytes) -> int:
        self.data.append(data)
        return len(data)

    def send(self, data: bytes) -> None:
        """Queue bytes as if the child had produced them."""
        self._inbound.append(data)

    async def read_bytes_async(self, size: int = 65536) -> bytes:
        return self._inbound.pop(0) if self._inbound else b""

    def resize(self, rows: int, cols: int) -> None:
        """Record a window-size change, as a PTY would apply one."""
        self.resizes.append((rows, cols))

    def configure_line(self, line: SerialLine) -> None:
        """Record the host line's settings, as a serial port would apply them."""
        self.lines.append(line)

    def flush(self) -> None:
        self.flush_count += 1

    def close(self) -> None:
        self.closed = True


class InboundLine:
    """Bytes a far-end device sends back up its cable, queued until the port reads them."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def read(self, size: int) -> bytes:
        data = await self._queue.get()
        if len(data) <= size:
            return data
        self._queue.put_nowait(data[size:])
        return data[:size]

    def send(self, data: bytes) -> None:
        self._queue.put_nowait(data)

    def take(self) -> bytes:
        """Everything sent that nobody has read yet, removed from the line."""
        data = bytearray()
        while not self._queue.empty():
            data += self._queue.get_nowait()
        return bytes(data)


class MemoryPrinter:
    """An in-memory duplex printer cable that keeps everything written to it, for tests."""

    def __init__(self, *, status: PrinterStatus = PrinterStatus.READY) -> None:
        self.data = bytearray()
        self.status = PrinterStatus(status)
        self.closed = False
        self.configuration: PrinterConfiguration | None = None
        self.configuration_history: list[PrinterConfiguration] = []
        self._inbound = InboundLine()

    def write_bytes(self, data: bytes) -> int:
        if self.closed:
            raise ValueError("printer is closed")
        self.data.extend(data)
        return len(data)

    async def read_bytes_async(self, size: int) -> bytes:
        return await self._inbound.read(size)

    def send_bytes(self, data: bytes) -> None:
        """Inject bytes arriving from the printer toward the host."""
        self._inbound.send(data)

    def take_inbound(self) -> bytes:
        """Everything the printer has sent that nobody has read yet, removed from the line."""
        return self._inbound.take()

    def configure(self, configuration: PrinterConfiguration) -> None:
        """Record a configuration snapshot, as a virtual adapter would."""
        self.configuration = configuration
        self.configuration_history.append(configuration)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class StreamPrinter:
    """Adapt a binary stream (file, serial object, pipe, socket file) as a printer."""

    def __init__(
        self,
        output: BinaryIO,
        input: BinaryIO | None = None,
        *,
        status: PrinterStatus = PrinterStatus.READY,
    ) -> None:
        self.output = output
        self.input = input
        self.status = status

    @property
    def closed(self) -> bool:
        return self.output.closed

    def write_bytes(self, data: bytes):
        return self.output.write(data)

    async def read_bytes_async(self, size: int) -> bytes:
        if self.input is None:
            return b""
        return await asyncio.to_thread(self.input.read, size)

    def configure(self, configuration: PrinterConfiguration) -> None:
        """A bare stream has no adapter to set."""

    def flush(self) -> None:
        self.output.flush()
