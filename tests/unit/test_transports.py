from bittty import HostPort


class RecordingTransport:
    def __init__(self):
        self.data = []
        self.flush_count = 0

    def write(self, data):
        self.data.append(data)
        return len(data)

    def flush(self):
        self.flush_count += 1


def test_host_port_ignores_writes_until_transport_is_attached():
    port = HostPort()

    assert port.connected is False
    assert port.write("abc") is None


def test_host_port_writes_and_flushes_attached_transport():
    transport = RecordingTransport()
    port = HostPort(transport)

    result = port.write("abc", flush=True)

    assert result == 3
    assert port.connected is True
    assert transport.data == ["abc"]
    assert transport.flush_count == 1


def test_host_port_can_detach_transport():
    transport = RecordingTransport()
    port = HostPort(transport)

    port.detach()
    port.write("abc", flush=True)

    assert port.connected is False
    assert transport.data == []
