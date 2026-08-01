from bittty import HostPort, MemoryConnection


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
