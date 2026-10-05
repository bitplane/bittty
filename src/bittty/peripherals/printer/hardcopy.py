"""The hardcopy terminal: a keyboard send/receive printer on the host line.

The LA120 DECwriter III is a terminal whose video is paper. Where a video terminal's
board parses the host's output into cells, this one prints it: the virtual printer's
pages are its display, and the printer's reports (DA, DSR) answer the host. It plugs
into the host line exactly where a board would, through a HostPort.
"""

from __future__ import annotations

from ...connections import Connection, HostPort
from .models import LA120
from .virtual import VirtualPrinter


class HardcopyTerminal:
    """A printer and a keyboard on the host line: what the host sends is printed, what is typed is sent.

    In full duplex the host echoes what it wants printed; with local echo the terminal prints
    what is typed as well.
    """

    def __init__(self, connection: Connection, *, printer: VirtualPrinter | None = None, local_echo: bool = False):
        self.printer = printer or VirtualPrinter(profile=LA120)
        self.local_echo = local_echo
        self.host = HostPort()
        self.host.attach(connection)

    def connect(self) -> None:
        """Start printing what arrives on the host line (needs a running event loop)."""
        self.host.connect(self.host.connection, self.receive)

    def disconnect(self) -> None:
        self.host.disconnect()

    def receive(self, data: bytes) -> None:
        """Print the host's output, and send any reply it asked for back up the line."""
        self.printer.write_bytes(data)
        replies = self.printer.take_inbound()
        if replies:
            self.host.write_bytes(replies, flush=True)

    def type(self, text: str) -> None:
        """Keys typed at the keyboard: sent to the host, and printed too under local echo."""
        self.host.write(text, flush=True)
        if self.local_echo:
            self.printer.write_bytes(text.encode("latin-1", errors="replace"))  # eight-bit: '?' for the rest
