"""The hardcopy terminal: a keyboard send/receive printer on the host line.

The LA120 DECwriter III is a terminal whose video is paper. Where a video terminal's
board parses the host's output into cells, this one prints it: the virtual printer's
pages are its display, and the printer's reports (DA, DSR) answer the host. It plugs
into the host line exactly where a board would, through a HostPort.
"""

from __future__ import annotations

from ...connections import Connection, HostPort
from .pages import PRINT_UNITS_PER_INCH, PrinterPageGeometry, PrinterRect
from .virtual import PrinterModel, VirtualPrinter

# Terminals & Printers Handbook ch. 14: "ESC [ c or ESC [ 0 c — LA120 transmits ESC [ ? 2 c",
# on fanfold paper up to 14 7/8 inches wide; the form length here is the usual 11 inches.
_FANFOLD = PrinterPageGeometry(
    width=PRINT_UNITS_PER_INCH * 119 // 8,
    height=PRINT_UNITS_PER_INCH * 11,
    printable_area=PrinterRect(0, 0, PRINT_UNITS_PER_INCH * 119 // 8, PRINT_UNITS_PER_INCH * 11),
)
LA120 = PrinterModel("la120", page_geometry=_FANFOLD, primary_device_attributes=(2,))


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

    def receive(self, data: bytes | str) -> None:
        """Print the host's output, and send any reply it asked for back up the line."""
        self._print(data)
        replies = self.printer.take_inbound()
        if replies:
            self.host.write_bytes(replies, flush=True)

    def type(self, text: str) -> None:
        """Keys typed at the keyboard: sent to the host, and printed too under local echo."""
        self.host.write(text, flush=True)
        if self.local_echo:
            self._print(text)

    def _print(self, data: bytes | str) -> None:
        """An eight-bit printer: text prints as Latin-1, and what that cannot hold as '?'."""
        self.printer.write_bytes(data.encode("latin-1", errors="replace") if isinstance(data, str) else data)
