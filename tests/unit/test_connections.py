import io

from bittty import Connection, HostPort, MemoryConnection, MemoryPrinter, PrinterConnection, StreamPrinter
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
