"""Reusable byte transports for the board's auxiliary printer port."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import IntEnum
from typing import BinaryIO

from .connections import PrinterStatus
from .printer_languages import (
    PrinterLanguage,
    VirtualPrinterState,
    _PrinterLanguageEngine,
)
from .printer_pages import (
    LETTER_PAGE_GEOMETRY,
    PrinterPage,
    PrinterPageGeometry,
    _PrinterPageStore,
)


class PrinterPortSelection(IntEnum):
    """Physical VT510 printer-port selection."""

    PARALLEL = 1
    COMM1 = 2
    COMM2 = 3


class PrinterType(IntEnum):
    """Physical printer language capability."""

    DEC_ANSI = 1
    PROPRINTER = 2
    DEC_AND_IBM = 3


class PrintedDataType(IntEnum):
    """Character repertoire emitted by the terminal."""

    NATIONAL = 1
    NATIONAL_LINE_DRAWING = 2
    MULTINATIONAL = 3
    ALL = 4


class ProPrinterCodePage(IntEnum):
    """IBM ProPrinter code pages accepted by DECSPPCS."""

    GREEK = 210
    SPANISH = 220
    PC_INTERNATIONAL = 437
    INTERNATIONAL = 437  # backward-friendly shorthand
    MULTILINGUAL = 850
    SLAVIC = 852
    TURKISH = 857
    PORTUGUESE = 860
    HEBREW = 862
    FRENCH_CANADIAN = 863
    DANISH = 865
    CYRILLIC = 866


class PrinterParity(IntEnum):
    """Serial parity selectors used by DECSPP."""

    NONE = 1
    EVEN = 2
    ODD = 3
    MARK = 6
    SPACE = 7


class PrinterFlowControl(IntEnum):
    """Serial flow-control selectors used by DECSFC."""

    XON_XOFF = 1
    DTR = 2
    BOTH = 3
    NONE = 4


class PrinterFlowThreshold(IntEnum):
    """Receive-flow threshold. Printers support the low threshold."""

    LOW = 1
    HIGH = 2


@dataclass(frozen=True)
class PrinterConfiguration:
    """Complete physical printer configuration exposed to an adapter."""

    port: PrinterPortSelection = PrinterPortSelection.PARALLEL
    printer_type: PrinterType = PrinterType.DEC_ANSI
    printed_data_type: PrintedDataType = PrintedDataType.NATIONAL
    code_page: ProPrinterCodePage = ProPrinterCodePage.PC_INTERNATIONAL
    baud_rate: int = 4800
    data_bits: int = 8
    parity: PrinterParity = PrinterParity.NONE
    stop_bits: int = 1
    transmit_flow_control: PrinterFlowControl = PrinterFlowControl.XON_XOFF
    receive_flow_control: PrinterFlowControl = PrinterFlowControl.XON_XOFF
    flow_threshold: PrinterFlowThreshold = PrinterFlowThreshold.LOW
    ignore_null: bool = False


class MemoryPrinter:
    """An in-memory duplex printer useful for virtual devices and tests."""

    def __init__(self, *, status: PrinterStatus = PrinterStatus.READY) -> None:
        self.data = bytearray()
        self.status = status
        self.closed = False
        self.configuration: PrinterConfiguration | None = None
        self.configuration_history: list[PrinterConfiguration] = []
        self._inbound: asyncio.Queue[bytes] = asyncio.Queue()

    def write_bytes(self, data: bytes) -> int:
        if self.closed:
            raise ValueError("printer is closed")
        self.data.extend(data)
        return len(data)

    async def read_bytes_async(self, size: int) -> bytes:
        data = await self._inbound.get()
        if len(data) <= size:
            return data
        self._inbound.put_nowait(data[size:])
        return data[:size]

    def send_bytes(self, data: bytes) -> None:
        """Inject bytes arriving from the printer toward the host."""
        self._inbound.put_nowait(data)

    def configure(self, configuration: PrinterConfiguration) -> None:
        """Record a configuration snapshot, as a virtual adapter would."""
        self.configuration = configuration
        self.configuration_history.append(configuration)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class VirtualPrinter(MemoryPrinter):
    """A duplex virtual printer with streaming printer-language state."""

    def __init__(
        self,
        device_type: PrinterType = PrinterType.DEC_ANSI,
        *,
        page_geometry: PrinterPageGeometry = LETTER_PAGE_GEOMETRY,
        status: PrinterStatus = PrinterStatus.READY,
    ) -> None:
        super().__init__(status=status)
        self._device_type = PrinterType(device_type)
        self._page_store = _PrinterPageStore(page_geometry)
        initial_language = (
            PrinterLanguage.IBM_PROPRINTER if self._device_type is PrinterType.PROPRINTER else PrinterLanguage.DEC_PPL
        )
        self._language_engine = _PrinterLanguageEngine(
            initial_language,
            supports_proprinter_switching=self._device_type is PrinterType.DEC_AND_IBM,
        )

    @property
    def device_type(self) -> PrinterType:
        """Return this virtual printer's immutable physical language capability."""
        return self._device_type

    @property
    def state(self) -> VirtualPrinterState:
        """Return an immutable snapshot of the interpreted printer state."""
        return self._language_engine.state

    @property
    def page_geometry(self) -> PrinterPageGeometry:
        """Return this printer's immutable physical sheet geometry."""
        return self._page_store.geometry

    @property
    def current_page(self) -> PrinterPage:
        """Return an immutable snapshot of the current page."""
        return self._page_store.current_page

    @property
    def completed_pages(self) -> tuple[PrinterPage, ...]:
        """Return completed pages without releasing them."""
        return self._page_store.completed_pages

    def take_completed_pages(self) -> tuple[PrinterPage, ...]:
        """Return completed pages and release the printer's references to them."""
        return self._page_store.take_completed_pages()

    def write_bytes(self, data: bytes) -> int:
        written = super().write_bytes(data)
        self._language_engine.feed(data)
        return written

    def reset(self) -> None:
        """Restore the physical printer's power-on language state."""
        self._language_engine.reset()


class StreamPrinter:
    """Adapt a binary stream (file, serial object, pipe, socket file) as a printer."""

    def __init__(
        self,
        output: BinaryIO,
        input: BinaryIO | None = None,
        *,
        status: PrinterStatus = PrinterStatus.READY,
    ) -> None:
        self.output = output
        self.input = input
        self.status = status

    @property
    def closed(self) -> bool:
        return bool(getattr(self.output, "closed", False))

    def write_bytes(self, data: bytes):
        return self.output.write(data)

    async def read_bytes_async(self, size: int) -> bytes:
        if self.input is None:
            return b""
        return await asyncio.to_thread(self.input.read, size)

    def flush(self) -> None:
        flusher = getattr(self.output, "flush", None)
        if callable(flusher):
            flusher()
