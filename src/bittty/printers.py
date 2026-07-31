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
    PRINT_UNITS_PER_INCH,
    PrinterControlToken,
    PrinterPage,
    PrinterPageGeometry,
    PrinterRect,
    PrinterTextRun,
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
        self._active_x = page_geometry.printable_area.left
        self._active_y = page_geometry.printable_area.top
        self._horizontal_advance = PRINT_UNITS_PER_INCH // 10
        self._vertical_advance = PRINT_UNITS_PER_INCH // 6
        self._pending_data = bytearray()
        self._pending_ascii = True
        self._pending_x = self._active_x
        self._pending_y = self._active_y
        self._pending_state: VirtualPrinterState | None = None
        self._pending_marks = False
        initial_language = (
            PrinterLanguage.IBM_PROPRINTER if self._device_type is PrinterType.PROPRINTER else PrinterLanguage.DEC_PPL
        )
        self._language_engine = _PrinterLanguageEngine(
            initial_language,
            supports_proprinter_switching=self._device_type is PrinterType.DEC_AND_IBM,
            on_printable=self._record_printable,
            on_control=self._record_control,
            on_crm_token=self._record_crm_token,
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
        self._flush_pending_run()
        return self._page_store.current_page

    @property
    def completed_pages(self) -> tuple[PrinterPage, ...]:
        """Return completed pages without releasing them."""
        return self._page_store.completed_pages

    def take_completed_pages(self) -> tuple[PrinterPage, ...]:
        """Return completed pages and release the printer's references to them."""
        return self._page_store.take_completed_pages()

    def _record_printable(self, data: bytes) -> None:
        if data.isascii():
            self._record_text_run(data, ascii_run=True)
            return
        start = 0
        size = len(data)
        while start < size:
            ascii_run = data[start] < 0x80
            end = start + 1
            while end < size and (data[end] < 0x80) == ascii_run:
                end += 1
            self._record_text_run(data[start:end], ascii_run=ascii_run)
            start = end

    def _record_text_run(self, data: bytes, *, ascii_run: bool) -> None:
        advance = len(data) * self._horizontal_advance
        state = self._language_engine.state
        blank = 0x20 if ascii_run else 0xA0
        marks = data.count(blank) != len(data)
        if self._pending_data and (
            self._pending_ascii != ascii_run or self._pending_state != state or self._pending_y != self._active_y
        ):
            self._flush_pending_run()
        if not self._pending_data:
            self._pending_ascii = ascii_run
            self._pending_x = self._active_x
            self._pending_y = self._active_y
            self._pending_state = state
            self._pending_marks = False
        self._pending_data.extend(data)
        self._pending_marks = self._pending_marks or marks
        self._active_x += advance

    def _record_control(self, byte: int) -> None:
        self._flush_pending_run()
        left = self._page_store.geometry.printable_area.left
        if byte == 0x08:  # BS
            self._active_x = max(left, self._active_x - self._horizontal_advance)
        elif byte == 0x09:  # HT; initial stops are columns 9, 17, ...
            column = max(0, (self._active_x - left) // self._horizontal_advance)
            self._active_x = left + (column // 8 + 1) * 8 * self._horizontal_advance
        elif byte == 0x0A:  # LF
            self._active_y += self._vertical_advance
            if self.state.control_representation or self.state.line_feed_new_line:
                self._active_x = left
        elif byte == 0x0B:  # VT; initial vertical stops occur every line
            self._active_y += self._vertical_advance
        elif byte == 0x0C:  # FF
            self._page_store.complete(force=True)
            self._active_y = self._page_store.geometry.printable_area.top
        elif byte == 0x0D:  # CR
            self._active_x = left
            if self.state.carriage_return_new_line:
                self._active_y += self._vertical_advance
        elif byte == 0x85:  # NEL
            self._active_x = left
            self._active_y += self._vertical_advance

    def _record_crm_token(self, source: bytes, text: str) -> None:
        self._flush_pending_run()
        advance = len(text) * self._horizontal_advance
        token = PrinterControlToken(
            PrinterRect(
                self._active_x,
                self._active_y,
                self._active_x + advance,
                self._active_y + self._vertical_advance,
            ),
            source,
            text,
            advance,
            self.state,
        )
        self._page_store.append(token)
        self._active_x += advance

    def _flush_pending_run(self) -> None:
        if not self._pending_data:
            return
        data = bytes(self._pending_data)
        advance = len(data) * self._horizontal_advance
        state = self._pending_state
        assert state is not None
        run = PrinterTextRun(
            PrinterRect(
                self._pending_x,
                self._pending_y,
                self._pending_x + advance,
                self._pending_y + self._vertical_advance,
            ),
            data,
            data.decode("ascii") if self._pending_ascii else None,
            advance,
            state,
        )
        self._page_store.append(run, marks=self._pending_marks)
        self._pending_data.clear()
        self._pending_state = None
        self._pending_marks = False

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
