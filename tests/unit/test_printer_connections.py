import asyncio
import io

import pytest

from bittty import Board, MemoryPrinter, PrinterPort, PrinterStatus, StreamPrinter


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
    class BrokenPrinter:
        status = PrinterStatus.OFFLINE

        def write_bytes(self, data):
            raise OSError("paper jam")

    port = PrinterPort(BrokenPrinter())
    assert port.status is PrinterStatus.OFFLINE
    assert port.write_bytes(b"test") is None
    assert port.status is PrinterStatus.NOT_READY


@pytest.mark.asyncio
async def test_duplex_memory_printer_pumps_input_to_the_host():
    board = Board()

    class Host:
        def __init__(self):
            self.data = []

        def write(self, data):
            self.data.append(data)

        def write_bytes(self, data):
            self.data.append(data)

    host = Host()
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
