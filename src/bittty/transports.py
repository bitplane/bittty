"""Transport ports for terminal host I/O."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .present import PresentEvent


@runtime_checkable
class WritableTransport(Protocol):
    """Transport that accepts terminal input/reply data."""

    def write(self, data: str):
        """Write data to the connected host."""


@runtime_checkable
class Presentable(Protocol):
    """A frontend that receives discrete present events from the board."""

    def present(self, event: "PresentEvent") -> None:
        """Handle one present event."""


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


class DisplayPort:
    """Cable between the board and an attached frontend (mirrors HostPort).

    The board pushes discrete present events here; when no frontend is attached
    present() is a no-op, so the backend runs headless exactly as before.
    """

    def __init__(self, frontend: Presentable | None = None) -> None:
        self.frontend = frontend

    def attach(self, frontend: Presentable) -> None:
        """Attach a frontend to receive present events."""
        self.frontend = frontend

    def detach(self) -> None:
        """Detach the current frontend."""
        self.frontend = None

    @property
    def connected(self) -> bool:
        """Whether a frontend is attached."""
        return self.frontend is not None

    def present(self, event: "PresentEvent") -> None:
        """Forward a present event to the attached frontend, if any."""
        if self.frontend is not None:
            self.frontend.present(event)
