"""Reusable byte transports for the board's auxiliary printer port."""

from __future__ import annotations

import asyncio
from typing import BinaryIO

from .connections import PrinterStatus


class MemoryPrinter:
    """An in-memory duplex printer useful for virtual devices and tests."""

    def __init__(self, *, status: PrinterStatus = PrinterStatus.READY) -> None:
        self.data = bytearray()
        self.status = status
        self.closed = False
        self._inbound: asyncio.Queue[bytes] = asyncio.Queue()

    def write_bytes(self, data: bytes) -> int:
        if self.closed:
            raise ValueError("printer is closed")
        self.data.extend(data)
        return len(data)

    async def read_bytes_async(self, size: int) -> bytes:
        data = await self._inbound.get()
        if len(data) <= size:
            return data
        self._inbound.put_nowait(data[size:])
        return data[:size]

    def send_bytes(self, data: bytes) -> None:
        """Inject bytes arriving from the printer toward the host."""
        self._inbound.put_nowait(data)

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
        return bool(getattr(self.output, "closed", False))

    def write_bytes(self, data: bytes):
        return self.output.write(data)

    async def read_bytes_async(self, size: int) -> bytes:
        if self.input is None:
            return b""
        return await asyncio.to_thread(self.input.read, size)

    def flush(self) -> None:
        flusher = getattr(self.output, "flush", None)
        if callable(flusher):
            flusher()
