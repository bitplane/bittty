"""Connections and the board-side ports they plug into."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .present import PresentEvent


@runtime_checkable
class Connection(Protocol):
    """A cable implementation (PTY, pipe, socket) that accepts terminal input/reply data."""

    def write(self, data: str):
        """Write data to the connected host."""


@runtime_checkable
class Presentable(Protocol):
    """A frontend that receives discrete present events from the board."""

    def present(self, event: "PresentEvent") -> None:
        """Handle one present event."""


class HostPort:
    """The board's jack toward the child program; a Connection (PTY, pipe) plugs in."""

    def __init__(self, connection: Connection | None = None) -> None:
        self.connection = connection

    def attach(self, connection: Connection) -> None:
        """Attach a connection to this host port."""
        self.connection = connection

    def detach(self) -> None:
        """Detach the current connection."""
        self.connection = None

    @property
    def connected(self) -> bool:
        """Whether a connection is attached."""
        return self.connection is not None

    def write(self, data: str, flush: bool = False):
        """Write data to the attached connection."""
        if self.connection is None:
            return None

        result = self.connection.write(data)
        if flush and hasattr(self.connection, "flush"):
            self.connection.flush()
        return result


class DisplayPort:
    """The board's jack toward the terminal (chrome); mirrors HostPort.

    The name is the video-connector pun, kept on purpose: the one place
    "display" survives in board vocabulary. The board pushes discrete present
    events here; when no terminal is attached present() is a no-op, so the
    board runs headless exactly as before.
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
