"""The virtual printer: a simulation of the box on the far end of the cable.

Tier 3 of the peripheral model (see docs/peripherals.md). Nothing here is part of
the terminal — the board runs identically with nothing plugged into its printer
port. Physical identity and report repertoire come from a PrinterModel, the
printer's equivalent of the terminal's Model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from ...connections import MemoryPrinter, PrinterStatus
from ...printer_config import PrinterConfiguration, PrinterType
from .languages import (
    PrinterLanguage,
    VirtualPrinterState,
    _PrinterLanguageEngine,
    _PrinterLayoutCommand,
    _PrinterReportCommand,
)
from .pages import (
    LETTER_PAGE_GEOMETRY,
    PRINT_UNITS_PER_INCH,
    PrinterBitImage,
    PrinterControlToken,
    PrinterDownloadedGlyph,
    PrinterPage,
    PrinterPageGeometry,
    PrinterRect,
    PrinterRenditionSpan,
    PrinterTextRun,
    _PrinterPageStore,
)


class PrinterUnsolicitedReports(Enum):
    """Status reports emitted when the virtual printer's condition changes."""

    DISABLED = "disabled"
    BRIEF = "brief"
    EXTENDED = "extended"


class PrinterMechanicalAction(Enum):
    """Observable physical actions produced by the virtual mechanism."""

    BELL = "bell"
    PAGE_EJECT = "page-eject"


@dataclass(frozen=True)
class PrinterMechanicalEvent:
    """One untimed mechanical action for a frontend or hardware bridge.

    These never reach the board. A real printer's bell rings at the printer, and
    a serial cable carries no signal for it — so they go to whoever plugged the
    printer in, never up the port. See docs/peripherals.md.
    """

    action: PrinterMechanicalAction
    page_number: int
    x: int
    y: int


@dataclass(frozen=True)
class PrinterModel:
    """Immutable physical identity and report capabilities of a virtual printer.

    Device-attribute tuples contain the parameters following ``CSI ?`` (DA) or
    ``CSI >`` (DA2).  Status tuples contain DEC PPL extended-report parameters;
    the virtual printer supplies the private CSI marker and the brief report.
    ``None`` means the model does not implement that report.
    """

    name: str
    device_type: PrinterType = PrinterType.DEC_ANSI
    page_geometry: PrinterPageGeometry = LETTER_PAGE_GEOMETRY
    primary_device_attributes: tuple[int, ...] | None = (72,)
    secondary_device_attributes: tuple[int, ...] | None = None
    ready_status_parameters: tuple[int, ...] = (20,)
    offline_status_parameters: tuple[int, ...] = (24,)
    unavailable_status_parameters: tuple[int, ...] = (59,)
    supports_cursor_position_report: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("profile name must not be empty")
        object.__setattr__(self, "device_type", PrinterType(self.device_type))
        for field_name in (
            "primary_device_attributes",
            "secondary_device_attributes",
            "ready_status_parameters",
            "offline_status_parameters",
            "unavailable_status_parameters",
        ):
            parameters = getattr(self, field_name)
            if parameters is None:
                if field_name.endswith("status_parameters"):
                    raise ValueError(f"{field_name} must contain one or more parameters from 0 to 999")
                continue
            parameters = tuple(parameters)
            if not parameters or any(parameter < 0 or parameter > 999 for parameter in parameters):
                raise ValueError(f"{field_name} must contain one or more parameters from 0 to 999")
            object.__setattr__(self, field_name, parameters)


GENERIC_DEC_PPL2_PRINTER = PrinterModel("generic-dec-ppl2")
GENERIC_PROPRINTER = PrinterModel(
    "generic-ibm-proprinter",
    device_type=PrinterType.PROPRINTER,
    primary_device_attributes=None,
)
GENERIC_DEC_AND_IBM_PRINTER = PrinterModel(
    "generic-dec-ppl2-and-ibm-proprinter",
    device_type=PrinterType.DEC_AND_IBM,
)


_DEFAULT_PROFILES = {
    PrinterType.DEC_ANSI: GENERIC_DEC_PPL2_PRINTER,
    PrinterType.PROPRINTER: GENERIC_PROPRINTER,
    PrinterType.DEC_AND_IBM: GENERIC_DEC_AND_IBM_PRINTER,
}


class VirtualPrinter(MemoryPrinter):
    """A duplex virtual printer with streaming printer-language state."""

    def __init__(
        self,
        device_type: PrinterType | None = None,
        *,
        profile: PrinterModel | None = None,
        page_geometry: PrinterPageGeometry | None = None,
        status: PrinterStatus = PrinterStatus.READY,
        on_actuate: Callable[[PrinterMechanicalEvent], None] | None = None,
    ) -> None:
        if profile is None:
            resolved_type = PrinterType.DEC_ANSI if device_type is None else PrinterType(device_type)
            profile = _DEFAULT_PROFILES[resolved_type]
        elif device_type is not None and PrinterType(device_type) is not profile.device_type:
            raise ValueError("device_type must match profile.device_type")
        page_geometry = profile.page_geometry if page_geometry is None else page_geometry
        self._profile = profile
        self._unsolicited_reports = PrinterUnsolicitedReports.DISABLED
        super().__init__(status=status)
        self._device_type = profile.device_type
        self._page_store = _PrinterPageStore(page_geometry)
        self._line_checkpoint = self._page_store.checkpoint()
        self.on_actuate = on_actuate
        self._mechanical_events: list[PrinterMechanicalEvent] = []
        self._downloaded_glyphs: dict[int, PrinterDownloadedGlyph] = {}
        self._active_x = page_geometry.printable_area.left
        self._active_y = page_geometry.printable_area.top
        self._left_margin = page_geometry.printable_area.left
        self._right_margin = page_geometry.printable_area.right
        self._top_margin = page_geometry.printable_area.top
        self._bottom_margin = page_geometry.printable_area.bottom
        self._right_margin_flag = False
        self._horizontal_advance = PRINT_UNITS_PER_INCH // 10
        self._ibm_base_horizontal_advance = self._horizontal_advance
        self._ibm_double_width = False
        self._ibm_perforation_skip = 0
        self._dec_layout_snapshot: tuple[object, ...] | None = None
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
        if initial_language is PrinterLanguage.IBM_PROPRINTER:
            self._vertical_tabs.clear()
        self._language_engine = _PrinterLanguageEngine(
            initial_language,
            supports_proprinter_switching=self._device_type is PrinterType.DEC_AND_IBM,
            on_printable=self._record_printable,
            on_control=self._record_control,
            on_crm_token=self._record_crm_token,
            on_layout=self._record_layout,
            on_report=self._record_report,
            on_bit_image=self._record_bit_image,
            on_font_download=self._record_font_download,
            on_reset=self._reset_layout,
        )

    @property
    def device_type(self) -> PrinterType:
        """Return this virtual printer's immutable physical language capability."""
        return self._device_type

    @property
    def profile(self) -> PrinterModel:
        """Return this printer's immutable model identity and capabilities."""
        return self._profile

    @property
    def unsolicited_reports(self) -> PrinterUnsolicitedReports:
        """Return the currently selected asynchronous status-report mode."""
        return self._unsolicited_reports

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

    @property
    def downloaded_glyphs(self) -> tuple[PrinterDownloadedGlyph, ...]:
        """Return the current IBM downloadable-character definitions by code point."""
        return tuple(self._downloaded_glyphs[code] for code in sorted(self._downloaded_glyphs))

    @property
    def mechanical_events(self) -> tuple[PrinterMechanicalEvent, ...]:
        """Return queued physical actions without consuming them.

        Empty while an on_actuate listener is attached: you either poll or you
        subscribe, and queueing for a subscriber nobody drains is a leak.
        """
        return tuple(self._mechanical_events)

    def take_mechanical_events(self) -> tuple[PrinterMechanicalEvent, ...]:
        """Return and clear queued physical actions."""
        events = tuple(self._mechanical_events)
        self._mechanical_events.clear()
        return events

    def _actuate(self, action: PrinterMechanicalAction, page_number: int) -> None:
        """Announce a physical action to a listener, or queue it for a poller."""
        event = PrinterMechanicalEvent(action, page_number, self._active_x, self._active_y)
        if self.on_actuate is None:
            self._mechanical_events.append(event)
        else:
            self.on_actuate(event)

    def configure(self, configuration: PrinterConfiguration) -> None:
        """Apply adapter configuration without changing the fixed printer identity."""
        super().configure(configuration)
        self._language_engine.set_ibm_code_page(configuration.code_page)

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
        self._line_checkpoint = self._page_store.checkpoint()

    def _form_feed(self) -> None:
        self._flush_pending_run()
        if self._no_forms:
            self._advance_line(home=False)
            return
        completed = self._page_store.complete(force=True)
        assert completed is not None
        self._actuate(PrinterMechanicalAction.PAGE_EJECT, completed.number)
        self._active_y = self._top_margin
        self._line_checkpoint = self._page_store.checkpoint()

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
            target = min(
                targets,
                default=self._active_x if self.state.language is PrinterLanguage.IBM_PROPRINTER else self._right_margin,
            )
            if target == self._active_x:
                return
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
                target = min(targets, default=None)
                if target is None and self.state.language is PrinterLanguage.IBM_PROPRINTER:
                    self._advance_line(home=self.state.carriage_return_new_line)
                elif target is not None:
                    self._active_y = target
                else:
                    self._active_y = self._last_vertical_position()
        elif byte == 0x0C:  # FF
            self._form_feed()
            if self.state.language is PrinterLanguage.IBM_PROPRINTER:
                self._active_x = self._left_margin
                self._right_margin_flag = False
        elif byte == 0x0D:  # CR
            self._active_x = self._left_margin
            self._right_margin_flag = False
            if self.state.carriage_return_new_line:
                self._advance_line(home=True)
            else:
                self._line_checkpoint = self._page_store.checkpoint()
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
        elif command is _PrinterLayoutCommand.IBM_HORIZONTAL_PITCH:
            self._set_ibm_horizontal_pitch(parameter)
        elif command is _PrinterLayoutCommand.IBM_LINE_SPACING:
            self._set_ibm_line_spacing(parameter)
            self._apply_ibm_perforation_skip()
        elif command is _PrinterLayoutCommand.IBM_VERTICAL_MOTION:
            self._ibm_vertical_motion(parameter)
            self._line_checkpoint = self._page_store.checkpoint()
        elif command is _PrinterLayoutCommand.IBM_DOUBLE_WIDTH:
            self._set_ibm_double_width(bool(parameter))
        elif command is _PrinterLayoutCommand.IBM_REPLACE_HORIZONTAL_TABS:
            self._horizontal_tabs.clear()
            self._set_tab_parameters(self._horizontal_tabs, parameters, horizontal=True)
        elif command is _PrinterLayoutCommand.IBM_REPLACE_VERTICAL_TABS:
            self._vertical_tabs.clear()
            self._set_tab_parameters(self._vertical_tabs, parameters, horizontal=False)
        elif command is _PrinterLayoutCommand.IBM_RESET_TABS:
            self._reset_ibm_tabs()
        elif command is _PrinterLayoutCommand.IBM_FORM_LENGTH_LINES:
            self._set_page_length(parameter)
            self._apply_ibm_perforation_skip()
        elif command is _PrinterLayoutCommand.IBM_FORM_LENGTH_INCHES:
            self._set_ibm_form_length_inches(parameter)
            self._apply_ibm_perforation_skip()
        elif command is _PrinterLayoutCommand.IBM_LANGUAGE_ENTER:
            self._save_dec_layout()
        elif command is _PrinterLayoutCommand.IBM_LANGUAGE_LEAVE:
            self._restore_dec_layout()
        elif command is _PrinterLayoutCommand.IBM_CANCEL_LINE:
            self._page_store.truncate(self._line_checkpoint)
        elif command is _PrinterLayoutCommand.IBM_SET_TOP_OF_FORM:
            self._set_ibm_top_of_form()
        elif command is _PrinterLayoutCommand.IBM_PERFORATION_SKIP:
            self._ibm_perforation_skip = parameter
            self._apply_ibm_perforation_skip()
        elif command is _PrinterLayoutCommand.IBM_BELL:
            self._actuate(PrinterMechanicalAction.BELL, self._page_store.current_page.number)

    def _record_bit_image(self, horizontal_dpi: int, pins: int, adjacent_dots: bool, data: bytes) -> None:
        self._flush_pending_run()
        bytes_per_column = pins // 8
        complete_size = len(data) - len(data) % bytes_per_column
        if complete_size == 0:
            return
        if not self._no_forms and self._active_y + pins * PRINT_UNITS_PER_INCH // 72 > self._bottom_margin:
            self._form_feed()
        column_advance = PRINT_UNITS_PER_INCH // horizontal_dpi
        available_columns = max(0, (self._right_margin - self._active_x) // column_advance)
        columns = min(complete_size // bytes_per_column, available_columns)
        if columns == 0:
            self._right_margin_flag = True
            return
        image_data = data[: columns * bytes_per_column]
        width = columns * column_advance
        height = pins * PRINT_UNITS_PER_INCH // 72
        self._page_store.append(
            PrinterBitImage(
                PrinterRect(
                    self._active_x,
                    self._active_y,
                    self._active_x + width,
                    self._active_y + height,
                ),
                image_data,
                horizontal_dpi,
                72,
                pins,
                adjacent_dots,
                self.state,
            ),
            marks=any(image_data),
        )
        self._active_x += width
        self._right_margin_flag = self._active_x >= self._right_margin

    def _record_font_download(self, data: bytes) -> None:
        if not data:
            self._downloaded_glyphs.clear()
            return
        if len(data) < 2 or (len(data) - 2) % 13:
            return
        start_code = data[1]
        for offset in range(2, len(data), 13):
            code_point = (start_code + (offset - 2) // 13) & 0xFF
            entry = data[offset : offset + 13]
            self._downloaded_glyphs[code_point] = PrinterDownloadedGlyph(code_point, entry[:2], entry[2:])

    def _record_report(self, command: _PrinterReportCommand) -> None:
        if command is _PrinterReportCommand.PRIMARY_ATTRIBUTES:
            self._flush_pending_run()
            self._send_parameter_report(b"\x1b[?", self.profile.primary_device_attributes, b"c")
        elif command is _PrinterReportCommand.SECONDARY_ATTRIBUTES:
            self._flush_pending_run()
            self._send_parameter_report(b"\x1b[>", self.profile.secondary_device_attributes, b"c")
        elif command is _PrinterReportCommand.EXTENDED_STATUS:
            self._send_status_report(extended=True)
        elif command is _PrinterReportCommand.DISABLE_UNSOLICITED_STATUS:
            self._unsolicited_reports = PrinterUnsolicitedReports.DISABLED
        elif command is _PrinterReportCommand.ENABLE_BRIEF_STATUS:
            self._unsolicited_reports = PrinterUnsolicitedReports.BRIEF
            self._send_status_report(extended=True)
        elif command is _PrinterReportCommand.ENABLE_EXTENDED_STATUS:
            self._unsolicited_reports = PrinterUnsolicitedReports.EXTENDED
            self._send_status_report(extended=True)
        elif command is _PrinterReportCommand.CURSOR_POSITION and self.profile.supports_cursor_position_report:
            self._flush_pending_run()
            area = self.page_geometry.printable_area
            row = (self._active_y - area.top) // self._vertical_advance + 1
            column = (self._active_x - area.left) // self._horizontal_advance + 1
            self.send_bytes(f"\x1b[{row};{column}R".encode("ascii"))

    def _send_parameter_report(self, prefix: bytes, parameters: tuple[int, ...] | None, final: bytes) -> None:
        if parameters is None:
            return
        body = b";".join(str(parameter).encode("ascii") for parameter in parameters)
        self.send_bytes(prefix + body + final)

    def _status_parameters(self) -> tuple[int, ...]:
        if self.status in (PrinterStatus.READY, PrinterStatus.ASSIGNED):
            return self.profile.ready_status_parameters
        if self.status is PrinterStatus.OFFLINE:
            return self.profile.offline_status_parameters
        return self.profile.unavailable_status_parameters

    def _send_status_report(self, *, extended: bool) -> None:
        parameters = self._status_parameters()
        error = self.status not in (PrinterStatus.READY, PrinterStatus.ASSIGNED)
        self.send_bytes(b"\x1b[3n" if error else b"\x1b[0n")
        if extended:
            self._send_parameter_report(b"\x1b[?", parameters, b"n")

    def _status_changed(self) -> None:
        if self._unsolicited_reports is not PrinterUnsolicitedReports.DISABLED:
            self._send_status_report(extended=self._unsolicited_reports is PrinterUnsolicitedReports.EXTENDED)

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
        self._ibm_base_horizontal_advance = self._horizontal_advance
        self._ibm_double_width = False
        self._ibm_perforation_skip = 0
        self._dec_layout_snapshot = None
        self._vertical_advance = PRINT_UNITS_PER_INCH // 6
        self._logical_page_bottom = area.bottom
        self._no_forms = False
        self._vertical_grid_pending = False
        self._horizontal_tabs, self._vertical_tabs = self._initial_tab_tables(
            area,
            self._horizontal_advance,
            self._vertical_advance,
        )
        if self.state.language is PrinterLanguage.IBM_PROPRINTER:
            self._vertical_tabs.clear()
        self._line_checkpoint = self._page_store.checkpoint()

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

    def _set_ibm_horizontal_pitch(self, tenths_cpi: int) -> None:
        if tenths_cpi <= 0:
            return
        self._ibm_base_horizontal_advance = round(PRINT_UNITS_PER_INCH * 10 / tenths_cpi)
        self._apply_ibm_horizontal_advance()

    def _set_ibm_double_width(self, enabled: bool) -> None:
        if self._ibm_double_width == enabled:
            return
        self._ibm_double_width = enabled
        self._apply_ibm_horizontal_advance()

    def _apply_ibm_horizontal_advance(self) -> None:
        self._flush_pending_run()
        self._horizontal_advance = self._ibm_base_horizontal_advance * (2 if self._ibm_double_width else 1)
        if self._active_x > self._right_margin:
            self._active_x = self._right_margin
            self._right_margin_flag = True

    def _set_ibm_line_spacing(self, units_216: int) -> None:
        if units_216 <= 0:
            return
        self._vertical_advance = units_216 * (PRINT_UNITS_PER_INCH // 216)
        self._vertical_grid_pending = False

    def _ibm_vertical_motion(self, units_216: int) -> None:
        if units_216 <= 0:
            return
        distance = units_216 * (PRINT_UNITS_PER_INCH // 216)
        target = self._active_y + distance
        if self._no_forms or target < self._bottom_margin:
            self._active_y = target
        else:
            self._form_feed()

    def _reset_ibm_tabs(self) -> None:
        area = self.page_geometry.printable_area
        capacity = area.width // self._horizontal_advance + 1
        self._horizontal_tabs = {
            area.left + (column - 1) * self._horizontal_advance for column in range(9, capacity + 1, 8)
        }
        self._vertical_tabs.clear()

    def _set_ibm_form_length_inches(self, inches: int) -> None:
        if inches <= 0:
            return
        area = self.page_geometry.printable_area
        self._no_forms = False
        self._logical_page_bottom = area.top + min(inches * PRINT_UNITS_PER_INCH, area.height)
        self._top_margin = area.top
        self._bottom_margin = self._logical_page_bottom

    def _set_ibm_top_of_form(self) -> None:
        area = self.page_geometry.printable_area
        form_length = max(self._vertical_advance, self._logical_page_bottom - self._top_margin)
        self._top_margin = min(max(self._active_y, area.top), area.bottom)
        self._logical_page_bottom = min(self._top_margin + form_length, area.bottom)
        self._apply_ibm_perforation_skip()

    def _apply_ibm_perforation_skip(self) -> None:
        if self._no_forms:
            return
        skipped = self._ibm_perforation_skip * self._vertical_advance
        self._bottom_margin = max(self._top_margin, self._logical_page_bottom - skipped)

    def _save_dec_layout(self) -> None:
        self._dec_layout_snapshot = (
            self._left_margin,
            self._right_margin,
            self._top_margin,
            self._bottom_margin,
            self._horizontal_advance,
            self._vertical_advance,
            self._logical_page_bottom,
            self._no_forms,
            self._vertical_grid_pending,
            self._horizontal_tabs.copy(),
            self._vertical_tabs.copy(),
        )
        area = self.page_geometry.printable_area
        self._left_margin = area.left
        self._right_margin = area.right
        self._top_margin = area.top
        self._bottom_margin = area.bottom
        self._horizontal_advance = PRINT_UNITS_PER_INCH // 10
        self._ibm_base_horizontal_advance = self._horizontal_advance
        self._ibm_double_width = False
        self._ibm_perforation_skip = 0
        self._vertical_advance = PRINT_UNITS_PER_INCH // 6
        self._logical_page_bottom = area.bottom
        self._no_forms = False
        self._vertical_grid_pending = False
        self._reset_ibm_tabs()
        self._active_x = min(max(self._active_x, self._left_margin), self._right_margin)
        self._active_y = max(self._active_y, self._top_margin)
        self._right_margin_flag = self._active_x >= self._right_margin

    def _restore_dec_layout(self) -> None:
        if self._dec_layout_snapshot is None:
            return
        (
            self._left_margin,
            self._right_margin,
            self._top_margin,
            self._bottom_margin,
            self._horizontal_advance,
            self._vertical_advance,
            self._logical_page_bottom,
            self._no_forms,
            self._vertical_grid_pending,
            horizontal_tabs,
            vertical_tabs,
        ) = self._dec_layout_snapshot
        self._horizontal_tabs = horizontal_tabs
        self._vertical_tabs = vertical_tabs
        self._ibm_base_horizontal_advance = PRINT_UNITS_PER_INCH // 10
        self._ibm_double_width = False
        self._active_x = min(max(self._active_x, self._left_margin), self._right_margin)
        self._active_y = max(self._active_y, self._top_margin)
        self._right_margin_flag = self._active_x >= self._right_margin
        self._dec_layout_snapshot = None

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
        self._unsolicited_reports = PrinterUnsolicitedReports.DISABLED
