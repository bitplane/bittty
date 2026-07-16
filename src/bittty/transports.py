"""Transport ports for terminal host I/O."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class WritableTransport(Protocol):
    """Transport that accepts terminal input/reply data."""

    def write(self, data: str):
        """Write data to the connected host."""


class HostPort:
    """Cable between terminal devices and an attached host transport."""

    def __init__(self, transport: WritableTransport | None = None) -> None:
        self.transport = transport

    def attach(self, transport: WritableTransport) -> None:
        """Attach a transport to this host port."""
        self.transport = transport

    def detach(self) -> None:
        """Detach the current transport."""
        self.transport = None

    @property
    def connected(self) -> bool:
        """Whether a transport is attached."""
        return self.transport is not None

    def write(self, data: str, flush: bool = False):
        """Write data to the attached transport."""
        if self.transport is None:
            return None

        result = self.transport.write(data)
        if flush and hasattr(self.transport, "flush"):
            self.transport.flush()
        return result
