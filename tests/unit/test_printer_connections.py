import asyncio
import io

import pytest

from bittty import Board, MemoryConnection, MemoryPrinter, PrinterPort, PrinterStatus, StreamPrinter


def test_memory_printer_and_stream_printer_are_binary():
    memory = MemoryPrinter()
    assert memory.write_bytes(b"\xff\x00") == 2
    assert bytes(memory.data) == b"\xff\x00"

    output = io.BytesIO()
    stream = StreamPrinter(output)
    assert stream.write_bytes(b"\xff\x00") == 2
    stream.flush()
    assert output.getvalue() == b"\xff\x00"


def test_printer_port_reports_connection_status_and_survives_failure():
    class JammedPrinter(MemoryPrinter):
        def write_bytes(self, data):
            raise OSError("paper jam")

    port = PrinterPort(JammedPrinter(status=PrinterStatus.OFFLINE))
    assert port.status is PrinterStatus.OFFLINE
    assert port.write_bytes(b"test") is None
    assert port.status is PrinterStatus.NOT_READY


@pytest.mark.asyncio
async def test_duplex_memory_printer_pumps_input_to_the_host():
    board = Board()

    host = MemoryConnection()
    board.host.attach(host)
    printer = MemoryPrinter()
    board.printer.connect(printer)
    board.parser.feed("\x1b[6i")
    printer.send_bytes(b"reply")

    for _ in range(10):
        if host.data:
            break
        await asyncio.sleep(0)

    board.printer.detach()
    assert host.data == [b"reply"]


@pytest.mark.asyncio
async def test_partial_printer_reads_preserve_byte_order():
    printer = MemoryPrinter()
    printer.send_bytes(b"abcdef")
    printer.send_bytes(b"XYZ")
    assert await printer.read_bytes_async(3) == b"abc"
    assert await printer.read_bytes_async(2) == b"de"
    assert printer.take_inbound() == b"fXYZ"
    printer.send_bytes(b"next")
    assert await printer.read_bytes_async(4) == b"next"
