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
    _PrinterLayoutCommand,
)
from .printer_pages import (
    LETTER_PAGE_GEOMETRY,
    PRINT_UNITS_PER_INCH,
    PrinterControlToken,
    PrinterPage,
    PrinterPageGeometry,
    PrinterRect,
    PrinterRenditionSpan,
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
        self._left_margin = page_geometry.printable_area.left
        self._right_margin = page_geometry.printable_area.right
        self._top_margin = page_geometry.printable_area.top
        self._bottom_margin = page_geometry.printable_area.bottom
        self._right_margin_flag = False
        self._horizontal_advance = PRINT_UNITS_PER_INCH // 10
        self._vertical_advance = PRINT_UNITS_PER_INCH // 6
        self._logical_page_bottom = page_geometry.printable_area.bottom
        self._no_forms = False
        self._vertical_grid_pending = False
        self._horizontal_tabs, self._vertical_tabs = self._initial_tab_tables(
            page_geometry.printable_area,
            self._horizontal_advance,
            self._vertical_advance,
        )
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
            on_layout=self._record_layout,
            on_reset=self._reset_layout,
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
        state = self._language_engine.state
        blank = 0x20 if ascii_run else 0xA0
        offset = 0
        size = len(data)
        while offset < size:
            if not self._prepare_to_image(state):
                return
            available = (self._right_margin - self._active_x) // self._horizontal_advance
            if available <= 0:
                self._right_margin_flag = True
                return
            end = min(size, offset + available)
            segment = data[offset:end]
            self._append_text_segment(
                segment,
                ascii_run=ascii_run,
                state=state,
                marks=segment.count(blank) != len(segment),
                completes_line=len(segment) == available,
            )
            offset = end

    def _append_text_segment(
        self,
        data: bytes,
        *,
        ascii_run: bool,
        state: VirtualPrinterState,
        marks: bool,
        completes_line: bool,
    ) -> None:
        advance = len(data) * self._horizontal_advance
        if self._pending_data and (
            self._pending_ascii != ascii_run or self._pending_state != state or self._pending_y != self._active_y
        ):
            self._flush_pending_run()
        if completes_line and not self._pending_data:
            self._store_text_run(
                data,
                ascii_run=ascii_run,
                x=self._active_x,
                y=self._active_y,
                state=state,
                marks=marks,
            )
            self._active_x += advance
            return
        if not self._pending_data:
            self._pending_ascii = ascii_run
            self._pending_x = self._active_x
            self._pending_y = self._active_y
            self._pending_state = state
            self._pending_marks = False
        self._pending_data.extend(data)
        self._pending_marks = self._pending_marks or marks
        self._active_x += advance
        if completes_line:
            self._flush_pending_run()

    def _prepare_to_image(self, state: VirtualPrinterState) -> bool:
        if self._right_margin - self._left_margin < self._horizontal_advance:
            self._right_margin_flag = True
            return False
        if not self._vertical_cell_fits(self._active_y):
            self._form_feed()
        if not self._right_margin_flag and self._active_x + self._horizontal_advance <= self._right_margin:
            return True
        if state.control_representation or state.autowrap:
            self._right_margin_flag = False
            self._advance_line(home=True)
            return self._active_x + self._horizontal_advance <= self._right_margin
        self._right_margin_flag = True
        return False

    def _vertical_cell_fits(self, top: int) -> bool:
        if self._no_forms:
            return True
        if self._bottom_margin - self._top_margin < self._vertical_advance:
            return top == self._top_margin
        return top + self._vertical_advance <= self._bottom_margin

    def _advance_line(self, *, home: bool) -> None:
        self._flush_pending_run()
        self._align_vertical_grid()
        if home:
            self._active_x = self._left_margin
            self._right_margin_flag = False
        next_y = self._active_y + self._vertical_advance
        if self._no_forms or self._vertical_cell_fits(next_y):
            self._active_y = next_y
        else:
            self._form_feed()

    def _form_feed(self) -> None:
        self._flush_pending_run()
        if self._no_forms:
            self._advance_line(home=False)
            return
        self._page_store.complete(force=True)
        self._active_y = self._top_margin

    def _record_control(self, byte: int) -> None:
        self._flush_pending_run()
        if byte == 0x08:  # BS
            if not self._right_margin_flag:
                self._active_x = max(self._left_margin, self._active_x - self._horizontal_advance)
        elif byte == 0x09:  # HT
            targets = (
                stop
                for stop in self._horizontal_tabs
                if self._active_x < stop < self._right_margin and stop >= self._left_margin
            )
            target = min(targets, default=self._right_margin)
            if target >= self._right_margin:
                self._active_x = self._right_margin
                self._right_margin_flag = True
            else:
                self._active_x = target
        elif byte == 0x0A:  # LF
            self._advance_line(home=self.state.control_representation or self.state.line_feed_new_line)
        elif byte == 0x0B:  # VT
            if self._no_forms:
                self._advance_line(home=False)
            else:
                self._align_vertical_grid()
                targets = (
                    stop
                    for stop in self._vertical_tabs
                    if self._active_y < stop <= self._last_vertical_position() and stop >= self._top_margin
                )
                self._active_y = min(targets, default=self._last_vertical_position())
        elif byte == 0x0C:  # FF
            self._form_feed()
        elif byte == 0x0D:  # CR
            self._active_x = self._left_margin
            self._right_margin_flag = False
            if self.state.carriage_return_new_line:
                self._advance_line(home=True)
        elif byte == 0x85:  # NEL
            self._advance_line(home=True)

    def _record_layout(self, command: _PrinterLayoutCommand, parameters: tuple[int, ...]) -> None:
        self._flush_pending_run()
        parameter = parameters[0] if parameters else 0
        if command is _PrinterLayoutCommand.HORIZONTAL_PITCH:
            self._set_horizontal_pitch(parameter)
        elif command is _PrinterLayoutCommand.VERTICAL_PITCH:
            self._set_vertical_pitch(parameter)
        elif command is _PrinterLayoutCommand.PAGE_LENGTH:
            self._set_page_length(parameter)
        elif command is _PrinterLayoutCommand.HORIZONTAL_MARGINS:
            self._set_horizontal_margins(*parameters)
        elif command is _PrinterLayoutCommand.VERTICAL_MARGINS:
            self._set_vertical_margins(*parameters)
        elif command is _PrinterLayoutCommand.HORIZONTAL_ABSOLUTE:
            self._horizontal_absolute(parameter)
        elif command is _PrinterLayoutCommand.HORIZONTAL_RELATIVE:
            self._horizontal_relative(parameter)
        elif command is _PrinterLayoutCommand.VERTICAL_ABSOLUTE:
            self._vertical_absolute(parameter)
        elif command is _PrinterLayoutCommand.VERTICAL_RELATIVE:
            self._vertical_relative(parameter)
        elif command is _PrinterLayoutCommand.SET_HORIZONTAL_TABS:
            self._set_tab_parameters(self._horizontal_tabs, parameters, horizontal=True)
        elif command is _PrinterLayoutCommand.SET_VERTICAL_TABS:
            self._set_tab_parameters(self._vertical_tabs, parameters, horizontal=False)
        elif command is _PrinterLayoutCommand.CLEAR_TABS:
            self._clear_tabs(parameters)
        elif command is _PrinterLayoutCommand.SET_HORIZONTAL_TAB_HERE:
            self._horizontal_tabs.add(self._active_x)
        elif command is _PrinterLayoutCommand.SET_VERTICAL_TAB_HERE:
            self._vertical_tabs.add(self._active_y)
        elif command is _PrinterLayoutCommand.CLEAR_HORIZONTAL_TABS:
            self._horizontal_tabs.clear()
        elif command is _PrinterLayoutCommand.CLEAR_VERTICAL_TABS:
            self._vertical_tabs.clear()

    def _reset_layout(self) -> None:
        self._flush_pending_run()
        area = self.page_geometry.printable_area
        self._active_x = area.left
        self._active_y = area.top
        self._left_margin = area.left
        self._right_margin = area.right
        self._top_margin = area.top
        self._bottom_margin = area.bottom
        self._right_margin_flag = False
        self._horizontal_advance = PRINT_UNITS_PER_INCH // 10
        self._vertical_advance = PRINT_UNITS_PER_INCH // 6
        self._logical_page_bottom = area.bottom
        self._no_forms = False
        self._vertical_grid_pending = False
        self._horizontal_tabs, self._vertical_tabs = self._initial_tab_tables(
            area,
            self._horizontal_advance,
            self._vertical_advance,
        )

    @staticmethod
    def _initial_tab_tables(
        area: PrinterRect, horizontal_advance: int, vertical_advance: int
    ) -> tuple[set[int], set[int]]:
        horizontal_capacity = area.width // (420 * 3) + 2
        vertical_capacity = area.height // (600 * 3) + 2
        horizontal_tabs = {
            area.left + (column - 1) * horizontal_advance for column in range(9, horizontal_capacity + 1, 8)
        }
        vertical_tabs = {area.top + (line - 1) * vertical_advance for line in range(1, vertical_capacity + 1)}
        return horizontal_tabs, vertical_tabs

    def _set_horizontal_pitch(self, parameter: int) -> None:
        advances = {
            0: 720 * 3,
            1: 720 * 3,
            2: 600 * 3,
            3: 545 * 3,
            4: 436 * 3,
            5: 1440 * 3,
            6: 1200 * 3,
            7: 1090 * 3,
            8: 872 * 3,
            9: 480 * 3,
            11: 420 * 3,
            12: 840 * 3,
            13: 400 * 3,
            14: 800 * 3,
            15: 720 * 3,
        }
        old_advance = self._horizontal_advance
        new_advance = advances.get(parameter)
        area = self.page_geometry.printable_area
        self._left_margin = area.left
        self._right_margin = area.right
        self._right_margin_flag = False
        if new_advance is None:
            return
        self._horizontal_advance = new_advance
        self._horizontal_tabs = {
            area.left + (stop - area.left) * new_advance // old_advance for stop in self._horizontal_tabs
        }
        self._active_x = self._grid_ceiling(self._active_x, area.left, new_advance)

    def _set_vertical_pitch(self, parameter: int) -> None:
        advances = {
            0: 1200 * 3,
            1: 1200 * 3,
            2: 900 * 3,
            3: 600 * 3,
            4: 3600 * 3,
            5: 2400 * 3,
            6: 1800 * 3,
            10: 1200 * 3,
            11: 1200 * 3,
            12: 900 * 3,
            13: 600 * 3,
            14: 3600 * 3,
            15: 2400 * 3,
            16: 1800 * 3,
            21: round(PRINT_UNITS_PER_INCH / 2.54 / 4),
            22: round(PRINT_UNITS_PER_INCH / 2.54 / 2),
            23: round(PRINT_UNITS_PER_INCH / 2.54),
            31: round(PRINT_UNITS_PER_INCH / 2.54 / 4),
            32: round(PRINT_UNITS_PER_INCH / 2.54 / 2),
            33: round(PRINT_UNITS_PER_INCH / 2.54),
        }
        new_advance = advances.get(parameter)
        if new_advance is None:
            return
        old_advance = self._vertical_advance
        origin = self.page_geometry.printable_area.top
        self._vertical_advance = new_advance
        self._vertical_tabs = {origin + (stop - origin) * new_advance // old_advance for stop in self._vertical_tabs}
        if not self._no_forms:
            self._top_margin = min(
                self._grid_ceiling(self._top_margin, origin, new_advance),
                self._logical_page_bottom,
            )
            self._bottom_margin = min(
                self._grid_ceiling(self._bottom_margin, origin, new_advance),
                self._logical_page_bottom,
            )
            self._vertical_grid_pending = True

    def _set_page_length(self, parameter: int) -> None:
        area = self.page_geometry.printable_area
        if parameter == 0:
            self._no_forms = True
            self._vertical_grid_pending = False
            return
        length = self._parameter_distance(parameter, horizontal=False)
        self._no_forms = False
        self._logical_page_bottom = area.top + min(length, area.height)
        self._top_margin = area.top
        self._bottom_margin = self._logical_page_bottom

    def _set_horizontal_margins(self, left: int, right: int) -> None:
        area = self.page_geometry.printable_area
        new_left = self._left_margin if left == 0 else self._parameter_position(left, horizontal=True)
        new_right = self._right_margin if right == 0 else (area.left + self._parameter_distance(right, horizontal=True))
        new_right = min(new_right, area.right)
        if new_left > new_right or new_left > area.right:
            return
        self._left_margin = new_left
        self._right_margin = new_right
        if self._active_x < new_left:
            self._active_x = new_left
        elif self._active_x > new_right:
            self._active_x = new_right
            self._right_margin_flag = True

    def _set_vertical_margins(self, top: int, bottom: int) -> None:
        if self._no_forms:
            return
        area = self.page_geometry.printable_area
        new_top = self._top_margin if top == 0 else self._parameter_position(top, horizontal=False)
        new_bottom = (
            self._bottom_margin if bottom == 0 else (area.top + self._parameter_distance(bottom, horizontal=False))
        )
        new_bottom = min(new_bottom, self._logical_page_bottom)
        if new_top > new_bottom or new_top > self._logical_page_bottom:
            return
        self._top_margin = new_top
        self._bottom_margin = new_bottom
        self._vertical_grid_pending = False
        if self._active_y < new_top:
            self._active_y = new_top
        elif self._active_y > self._last_vertical_position():
            self._form_feed()

    def _horizontal_absolute(self, parameter: int) -> None:
        target = self._parameter_position(max(1, parameter), horizontal=True)
        target = max(target, self._left_margin)
        if target > self._right_margin:
            target = self._right_margin
            self._right_margin_flag = True
        self._record_lined_motion(self._active_x, target)
        self._active_x = target
        if target < self._right_margin:
            self._right_margin_flag = False

    def _horizontal_relative(self, parameter: int) -> None:
        if self._right_margin_flag:
            return
        target = self._active_x + self._parameter_distance(max(1, parameter), horizontal=True)
        if target > self._right_margin:
            target = self._right_margin
            self._right_margin_flag = True
        self._record_lined_motion(self._active_x, target)
        self._active_x = target

    def _record_lined_motion(self, start: int, end: int) -> None:
        rendition = self.state.rendition
        if start == end or not rendition.has_lining:
            return
        self._page_store.append(
            PrinterRenditionSpan(
                PrinterRect(
                    min(start, end),
                    self._active_y,
                    max(start, end),
                    self._active_y + self._vertical_advance,
                ),
                self.state,
            )
        )

    def _vertical_absolute(self, parameter: int) -> None:
        if self._no_forms:
            self._advance_line(home=False)
            return
        self._align_vertical_grid()
        target = self._parameter_position(max(1, parameter), horizontal=False)
        if target < self._active_y:
            return
        self._active_y = min(max(target, self._top_margin), self._last_vertical_position())

    def _vertical_relative(self, parameter: int) -> None:
        self._align_vertical_grid()
        count = max(1, parameter)
        if self._no_forms:
            count = min(count, 255)
        target = self._active_y + self._parameter_distance(count, horizontal=False)
        self._active_y = target if self._no_forms else min(target, self._last_vertical_position())

    def _set_tab_parameters(self, table: set[int], parameters: tuple[int, ...], *, horizontal: bool) -> None:
        for parameter in parameters:
            if parameter > 0:
                table.add(self._parameter_position(parameter, horizontal=horizontal))

    def _clear_tabs(self, parameters: tuple[int, ...]) -> None:
        for parameter in parameters:
            if parameter == 0:
                self._horizontal_tabs.discard(self._active_x)
            elif parameter == 1:
                self._align_vertical_grid()
                self._vertical_tabs.discard(self._active_y)
            elif parameter in (2, 3):
                self._horizontal_tabs.clear()
            elif parameter == 4:
                self._vertical_tabs.clear()

    def _parameter_distance(self, parameter: int, *, horizontal: bool) -> int:
        if self.state.position_unit_mode:
            return parameter * (PRINT_UNITS_PER_INCH // 720)
        return parameter * (self._horizontal_advance if horizontal else self._vertical_advance)

    def _parameter_position(self, parameter: int, *, horizontal: bool) -> int:
        area = self.page_geometry.printable_area
        origin = area.left if horizontal else area.top
        return origin + self._parameter_distance(max(1, parameter) - 1, horizontal=horizontal)

    def _align_vertical_grid(self) -> None:
        if not self._vertical_grid_pending:
            return
        self._active_y = self._grid_ceiling(
            self._active_y,
            self.page_geometry.printable_area.top,
            self._vertical_advance,
        )
        self._vertical_grid_pending = False

    def _last_vertical_position(self) -> int:
        if self._bottom_margin - self._top_margin < self._vertical_advance:
            return self._top_margin
        return self._bottom_margin - self._vertical_advance

    @staticmethod
    def _grid_ceiling(value: int, origin: int, increment: int) -> int:
        if value <= origin:
            return origin
        return origin + (value - origin + increment - 1) // increment * increment

    def _record_crm_token(self, source: bytes, text: str) -> None:
        self._flush_pending_run()
        state = self.state
        offset = 0
        while offset < len(text):
            if not self._prepare_to_image(state):
                return
            available = (self._right_margin - self._active_x) // self._horizontal_advance
            if available <= 0:
                self._right_margin_flag = True
                return
            end = min(len(text), offset + available)
            segment = text[offset:end]
            advance = len(segment) * self._horizontal_advance
            token = PrinterControlToken(
                PrinterRect(
                    self._active_x,
                    self._active_y,
                    self._active_x + advance,
                    self._active_y + self._vertical_advance,
                ),
                source,
                segment,
                advance,
                state,
            )
            self._page_store.append(token)
            self._active_x += advance
            offset = end

    def _flush_pending_run(self) -> None:
        if not self._pending_data:
            return
        data = bytes(self._pending_data)
        state = self._pending_state
        assert state is not None
        self._store_text_run(
            data,
            ascii_run=self._pending_ascii,
            x=self._pending_x,
            y=self._pending_y,
            state=state,
            marks=self._pending_marks,
        )
        self._pending_data.clear()
        self._pending_state = None
        self._pending_marks = False

    def _store_text_run(
        self,
        data: bytes,
        *,
        ascii_run: bool,
        x: int,
        y: int,
        state: VirtualPrinterState,
        marks: bool,
    ) -> None:
        advance = len(data) * self._horizontal_advance
        run = PrinterTextRun(
            PrinterRect(
                x,
                y,
                x + advance,
                y + self._vertical_advance,
            ),
            data,
            data.decode("ascii") if ascii_run else None,
            advance,
            state,
        )
        self._page_store.append(run, marks=marks)

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
