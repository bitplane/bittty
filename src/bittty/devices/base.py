"""Base class shared by board devices."""

from __future__ import annotations

from ..operations import Operation


class Device:
    """A board device: dispatches an operation to its name -> handler table."""

    handlers: dict

    def handle_operation(self, operation: Operation) -> None:
        handler = self.handlers.get(operation.name)
        if handler is not None:
            handler(operation)
