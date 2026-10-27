import asyncio
import io

import pytest

from bittty import Board, Connection, HostPort, MemoryConnection, MemoryPrinter, PrinterConnection, StreamPrinter
from bittty.peripherals.printer import VirtualPrinter
from bittty.pty import PTY, StdioPTY


def test_host_port_ignores_writes_until_connection_is_attached():
    port = HostPort()

    assert port.connected is False
    assert port.write("abc") is None


def test_host_port_writes_and_flushes_attached_connection():
    connection = MemoryConnection()
    port = HostPort(connection)

    result = port.write("abc", flush=True)

    assert result == 3
    assert port.connected is True
    assert connection.data == ["abc"]
    assert connection.flush_count == 1


def test_host_port_can_detach_connection():
    connection = MemoryConnection()
    port = HostPort(connection)

    port.detach()
    port.write("abc", flush=True)

    assert port.connected is False
    assert connection.data == []


def test_every_host_cable_implements_the_whole_connection_protocol():
    """The ports call these methods directly, so no cable may leave one out."""
    cables = [MemoryConnection(), StdioPTY(io.BytesIO(), io.BytesIO()), PTY()]
    assert all(isinstance(cable, Connection) for cable in cables)


def test_every_printer_cable_implements_the_whole_printer_protocol():
    cables = [MemoryPrinter(), StreamPrinter(io.BytesIO()), VirtualPrinter()]
    assert all(isinstance(cable, PrinterConnection) for cable in cables)


def test_a_partial_cable_is_not_a_connection():
    class WriteOnly:
        def write(self, data):
            return len(data)

    assert not isinstance(WriteOnly(), Connection)


@pytest.mark.asyncio
async def test_reconnect_retires_old_reader_and_discards_its_pending_data():
    class PendingCable(MemoryConnection):
        def __init__(self):
            super().__init__()
            self.waiting = asyncio.Event()
            self.incoming = asyncio.Queue()

        async def read_bytes_async(self, size):
            self.waiting.set()
            try:
                return await self.incoming.get()
            except asyncio.CancelledError:
                return b"stale"

    old = PendingCable()
    new = PendingCable()
    port = HostPort()
    received = []
    port.connect(old, received.append)
    first = port._reader_task
    await old.waiting.wait()
    port.connect(new, received.append)
    new.incoming.put_nowait(b"fresh")
    for _ in range(10):
        await asyncio.sleep(0)
    port.disconnect()
    first.cancel()
    await asyncio.sleep(0)
    assert first.done()
    assert received == [b"fresh"]


@pytest.mark.asyncio
async def test_reconnecting_same_cable_keeps_pending_read_and_rebinds_callback():
    class PendingCable(MemoryConnection):
        def __init__(self):
            super().__init__()
            self.waiting = asyncio.Event()
            self.incoming = asyncio.Queue()

        async def read_bytes_async(self, size):
            self.waiting.set()
            return await self.incoming.get()

    cable = PendingCable()
    port = HostPort()
    old, new = [], []
    port.connect(cable, old.append)
    reader = port._reader_task
    await cable.waiting.wait()
    port.connect(cable, new.append)
    assert port._reader_task is reader
    cable.incoming.put_nowait(b"pending output")
    for _ in range(10):
        await asyncio.sleep(0)
    port.disconnect()
    await asyncio.sleep(0)
    assert old == []
    assert new == [b"pending output"]


@pytest.mark.asyncio
async def test_board_reconnect_starts_reader_for_new_cable():
    board = Board()
    old = MemoryConnection()
    new = MemoryConnection([b"new cable"])
    board.connect(old)
    first = board.host._reader_task
    await asyncio.sleep(0)
    board.connect(new)
    for _ in range(10):
        await asyncio.sleep(0)
    board.stop_process()
    assert first.done()
    assert board.capture_text() == "new cable"
