"""The virtual printer: a simulation of the box on the far end of the cable.

Tier 3 of the peripheral model (see docs/peripherals.md). Nothing here is part of
the terminal — the board runs identically with nothing plugged into its printer
port. Physical identity and report repertoire come from a PrinterModel, the
printer's equivalent of the terminal's Model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum

from ...connections import InboundLine, PrinterStatus
from ...connections.printer_config import PrinterConfiguration, PrinterType
from .languages import (
    PrinterLanguage,
    VirtualPrinterState,
    _PrinterLanguageEngine,
    _PrinterLayoutCommand,
    _PrinterReportCommand,
)
from .models import DEFAULT_MODELS, PrinterModel
from .pages import (
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


@dataclass
class _Layout:
    """The page layout a printer language programs: margins, pitch, form length and tab stops.

    Power-on and a language reset build a fresh one. Entering the IBM language sets the
    DEC layout aside whole, rather than field by field.
    """

    left_margin: int
    right_margin: int
    top_margin: int
    bottom_margin: int
    logical_page_bottom: int
    horizontal_advance: int = PRINT_UNITS_PER_INCH // 10
    vertical_advance: int = PRINT_UNITS_PER_INCH // 6
    ibm_base_horizontal_advance: int = PRINT_UNITS_PER_INCH // 10
    ibm_double_width: bool = False
    ibm_perforation_skip: int = 0
    no_forms: bool = False
    vertical_grid_pending: bool = False
    horizontal_tabs: set[int] = field(default_factory=set)
    vertical_tabs: set[int] = field(default_factory=set)

    @classmethod
    def power_on(cls, area: PrinterRect, language: PrinterLanguage) -> _Layout:
        """10 pitch, 6 lines per inch, the whole printable area, and the power-on tab stops.

        Horizontal stops every eight columns; vertical stops on every line, except under
        the IBM language, which powers on with none.
        """
        layout = cls(area.left, area.right, area.top, area.bottom, area.bottom)
        columns = area.width // (420 * 3) + 2
        layout.horizontal_tabs = {
            area.left + (column - 1) * layout.horizontal_advance for column in range(9, columns + 1, 8)
        }
        if language is not PrinterLanguage.IBM_PROPRINTER:
            lines = area.height // (600 * 3) + 2
            layout.vertical_tabs = {area.top + (line - 1) * layout.vertical_advance for line in range(1, lines + 1)}
        return layout


class VirtualPrinter:
    """A duplex virtual printer with streaming printer-language state.

    It keeps pages, not bytes: pass trace=True to also keep every byte received in
    `trace`, which otherwise would grow for as long as the child prints.
    """

    def __init__(
        self,
        device_type: PrinterType | None = None,
        *,
        profile: PrinterModel | None = None,
        page_geometry: PrinterPageGeometry | None = None,
        status: PrinterStatus = PrinterStatus.READY,
        on_actuate: Callable[[PrinterMechanicalEvent], None] | None = None,
        trace: bool = False,
    ) -> None:
        if profile is None:
            resolved_type = PrinterType.DEC_ANSI if device_type is None else PrinterType(device_type)
            profile = DEFAULT_MODELS[resolved_type]
        elif device_type is not None and PrinterType(device_type) is not profile.device_type:
            raise ValueError("device_type must match profile.device_type")
        page_geometry = profile.page_geometry if page_geometry is None else page_geometry
        self._profile = profile
        self._unsolicited_reports = PrinterUnsolicitedReports.DISABLED
        self._status = PrinterStatus(status)
        self.closed = False
        self.configuration: PrinterConfiguration | None = None
        self.trace: bytearray | None = bytearray() if trace else None
        self._inbound = InboundLine()
        self._device_type = profile.device_type
        self._page_store = _PrinterPageStore(page_geometry)
        self._line_checkpoint = self._page_store.checkpoint()
        self.on_actuate = on_actuate
        self._mechanical_events: list[PrinterMechanicalEvent] = []
        self._downloaded_glyphs: dict[int, PrinterDownloadedGlyph] = {}
        initial_language = (
            PrinterLanguage.IBM_PROPRINTER if self._device_type is PrinterType.PROPRINTER else PrinterLanguage.DEC_PPL
        )
        # The print head, and the layout the language has programmed around it.
        self._active_x = page_geometry.printable_area.left
        self._active_y = page_geometry.printable_area.top
        self._right_margin_flag = False
        self._layout = _Layout.power_on(page_geometry.printable_area, initial_language)
        self._dec_layout: _Layout | None = None  # the DEC layout, set aside while the IBM language runs
        self._pending_data = bytearray()
        self._pending_ascii = True
        self._pending_x = self._active_x
        self._pending_y = self._active_y
        self._pending_state: VirtualPrinterState | None = None
        self._pending_marks = False
        self._layout_commands = self._layout_command_table()
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

        Nothing queues while an on_actuate listener is attached: you either poll
        or you subscribe, and queueing for a subscriber nobody drains is a leak.
        Events from before a late attach stay here until taken.
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

    # --- the cable's far end --- #

    @property
    def status(self) -> PrinterStatus:
        return self._status

    @status.setter
    def status(self, status: PrinterStatus) -> None:
        status = PrinterStatus(status)
        previous = self._status
        self._status = status
        if status is not previous:
            self._status_changed()

    async def read_bytes_async(self, size: int) -> bytes:
        return await self._inbound.read(size)

    def send_bytes(self, data: bytes) -> None:
        """Send bytes from the printer toward the host."""
        self._inbound.send(data)

    def take_inbound(self) -> bytes:
        """Everything the printer has sent that nobody has read yet, removed from the line."""
        return self._inbound.take()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def configure(self, configuration: PrinterConfiguration) -> None:
        """Apply adapter configuration without changing the fixed printer identity."""
        self.configuration = configuration
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
            available = (self._layout.right_margin - self._active_x) // self._layout.horizontal_advance
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
        advance = len(data) * self._layout.horizontal_advance
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
        if self._layout.right_margin - self._layout.left_margin < self._layout.horizontal_advance:
            self._right_margin_flag = True
            return False
        if not self._vertical_cell_fits(self._active_y):
            self._form_feed()
        if (
            not self._right_margin_flag
            and self._active_x + self._layout.horizontal_advance <= self._layout.right_margin
        ):
            return True
        if state.control_representation or state.autowrap:
            self._right_margin_flag = False
            self._advance_line(home=True)
            return self._active_x + self._layout.horizontal_advance <= self._layout.right_margin
        self._right_margin_flag = True
        return False

    def _vertical_cell_fits(self, top: int) -> bool:
        if self._layout.no_forms:
            return True
        if self._layout.bottom_margin - self._layout.top_margin < self._layout.vertical_advance:
            return top == self._layout.top_margin
        return top + self._layout.vertical_advance <= self._layout.bottom_margin

    def _advance_line(self, *, home: bool) -> None:
        self._flush_pending_run()
        self._align_vertical_grid()
        if home:
            self._active_x = self._layout.left_margin
            self._right_margin_flag = False
        next_y = self._active_y + self._layout.vertical_advance
        if self._layout.no_forms or self._vertical_cell_fits(next_y):
            self._active_y = next_y
        else:
            self._form_feed()
        self._line_checkpoint = self._page_store.checkpoint()

    def _form_feed(self) -> None:
        self._flush_pending_run()
        if self._layout.no_forms:
            self._advance_line(home=False)
            return
        completed = self._page_store.complete(force=True)
        assert completed is not None
        self._actuate(PrinterMechanicalAction.PAGE_EJECT, completed.number)
        self._active_y = self._layout.top_margin
        self._line_checkpoint = self._page_store.checkpoint()

    def _record_control(self, byte: int) -> None:
        self._flush_pending_run()
        if byte == 0x08:  # BS
            if not self._right_margin_flag:
                self._active_x = max(self._layout.left_margin, self._active_x - self._layout.horizontal_advance)
        elif byte == 0x09:  # HT
            targets = (
                stop
                for stop in self._layout.horizontal_tabs
                if self._active_x < stop < self._layout.right_margin and stop >= self._layout.left_margin
            )
            target = min(
                targets,
                default=self._active_x
                if self.state.language is PrinterLanguage.IBM_PROPRINTER
                else self._layout.right_margin,
            )
            if target == self._active_x:
                return
            if target >= self._layout.right_margin:
                self._active_x = self._layout.right_margin
                self._right_margin_flag = True
            else:
                self._active_x = target
        elif byte == 0x0A:  # LF
            self._advance_line(home=self.state.control_representation or self.state.line_feed_new_line)
        elif byte == 0x0B:  # VT
            if self._layout.no_forms:
                self._advance_line(home=False)
            else:
                self._align_vertical_grid()
                targets = (
                    stop
                    for stop in self._layout.vertical_tabs
                    if self._active_y < stop <= self._last_vertical_position() and stop >= self._layout.top_margin
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
                self._active_x = self._layout.left_margin
                self._right_margin_flag = False
        elif byte == 0x0D:  # CR
            self._active_x = self._layout.left_margin
            self._right_margin_flag = False
            if self.state.carriage_return_new_line:
                self._advance_line(home=True)
            else:
                self._line_checkpoint = self._page_store.checkpoint()
        elif byte == 0x85:  # NEL
            self._advance_line(home=True)

    def _layout_command_table(self) -> dict[_PrinterLayoutCommand, Callable[[int, tuple[int, ...]], None]]:
        """What each layout command does, given its first parameter (0 if none) and all of them."""
        C = _PrinterLayoutCommand
        return {
            C.HORIZONTAL_PITCH: lambda p, ps: self._set_horizontal_pitch(p),
            C.VERTICAL_PITCH: lambda p, ps: self._set_vertical_pitch(p),
            C.PAGE_LENGTH: lambda p, ps: self._set_page_length(p),
            C.HORIZONTAL_MARGINS: lambda p, ps: self._set_horizontal_margins(*ps),
            C.VERTICAL_MARGINS: lambda p, ps: self._set_vertical_margins(*ps),
            C.HORIZONTAL_ABSOLUTE: lambda p, ps: self._horizontal_absolute(p),
            C.HORIZONTAL_RELATIVE: lambda p, ps: self._horizontal_relative(p),
            C.VERTICAL_ABSOLUTE: lambda p, ps: self._vertical_absolute(p),
            C.VERTICAL_RELATIVE: lambda p, ps: self._vertical_relative(p),
            C.SET_HORIZONTAL_TABS: lambda p, ps: self._set_tab_parameters(
                self._layout.horizontal_tabs, ps, horizontal=True
            ),
            C.SET_VERTICAL_TABS: lambda p, ps: self._set_tab_parameters(
                self._layout.vertical_tabs, ps, horizontal=False
            ),
            C.CLEAR_TABS: lambda p, ps: self._clear_tabs(ps),
            C.SET_HORIZONTAL_TAB_HERE: lambda p, ps: self._layout.horizontal_tabs.add(self._active_x),
            C.SET_VERTICAL_TAB_HERE: lambda p, ps: self._layout.vertical_tabs.add(self._active_y),
            C.CLEAR_HORIZONTAL_TABS: lambda p, ps: self._layout.horizontal_tabs.clear(),
            C.CLEAR_VERTICAL_TABS: lambda p, ps: self._layout.vertical_tabs.clear(),
            # The language engine keeps the unit mode; _parameter_distance reads it from state.
            C.POSITION_UNIT_MODE: lambda p, ps: None,
            C.IBM_HORIZONTAL_PITCH: lambda p, ps: self._set_ibm_horizontal_pitch(p),
            C.IBM_LINE_SPACING: lambda p, ps: self._set_ibm_line_spacing(p),
            C.IBM_VERTICAL_MOTION: lambda p, ps: self._ibm_vertical_motion(p),
            C.IBM_DOUBLE_WIDTH: lambda p, ps: self._set_ibm_double_width(bool(p)),
            C.IBM_REPLACE_HORIZONTAL_TABS: lambda p, ps: self._replace_tabs(
                self._layout.horizontal_tabs, ps, horizontal=True
            ),
            C.IBM_REPLACE_VERTICAL_TABS: lambda p, ps: self._replace_tabs(
                self._layout.vertical_tabs, ps, horizontal=False
            ),
            C.IBM_RESET_TABS: lambda p, ps: self._reset_ibm_tabs(),
            C.IBM_FORM_LENGTH_LINES: lambda p, ps: self._set_ibm_form_length_lines(p),
            C.IBM_FORM_LENGTH_INCHES: lambda p, ps: self._set_ibm_form_length_inches(p),
            C.IBM_LANGUAGE_ENTER: lambda p, ps: self._save_dec_layout(),
            C.IBM_LANGUAGE_LEAVE: lambda p, ps: self._restore_dec_layout(),
            C.IBM_CANCEL_LINE: lambda p, ps: self._page_store.truncate(self._line_checkpoint),
            C.IBM_SET_TOP_OF_FORM: lambda p, ps: self._set_ibm_top_of_form(),
            C.IBM_PERFORATION_SKIP: lambda p, ps: self._set_ibm_perforation_skip(p),
            C.IBM_BELL: lambda p, ps: self._actuate(PrinterMechanicalAction.BELL, self._page_store.current_page.number),
        }

    def _record_layout(self, command: _PrinterLayoutCommand, parameters: tuple[int, ...]) -> None:
        self._flush_pending_run()
        self._layout_commands[command](parameters[0] if parameters else 0, parameters)

    def _replace_tabs(self, table: set[int], parameters: tuple[int, ...], *, horizontal: bool) -> None:
        table.clear()
        self._set_tab_parameters(table, parameters, horizontal=horizontal)

    def _set_ibm_perforation_skip(self, lines: int) -> None:
        self._layout.ibm_perforation_skip = lines
        self._apply_ibm_perforation_skip()

    def _record_bit_image(self, horizontal_dpi: int, pins: int, adjacent_dots: bool, data: bytes) -> None:
        self._flush_pending_run()
        bytes_per_column = pins // 8
        complete_size = len(data) - len(data) % bytes_per_column
        if complete_size == 0:
            return
        if (
            not self._layout.no_forms
            and self._active_y + pins * PRINT_UNITS_PER_INCH // 72 > self._layout.bottom_margin
        ):
            self._form_feed()
        column_advance = PRINT_UNITS_PER_INCH // horizontal_dpi
        available_columns = max(0, (self._layout.right_margin - self._active_x) // column_advance)
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
        self._right_margin_flag = self._active_x >= self._layout.right_margin

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
            row = (self._active_y - area.top) // self._layout.vertical_advance + 1
            column = (self._active_x - area.left) // self._layout.horizontal_advance + 1
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
        self._right_margin_flag = False
        self._layout = _Layout.power_on(area, self.state.language)
        self._dec_layout = None
        self._line_checkpoint = self._page_store.checkpoint()

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
        old_advance = self._layout.horizontal_advance
        new_advance = advances.get(parameter)
        area = self.page_geometry.printable_area
        self._layout.left_margin = area.left
        self._layout.right_margin = area.right
        self._right_margin_flag = False
        if new_advance is None:
            return
        self._layout.horizontal_advance = new_advance
        self._layout.horizontal_tabs = {
            area.left + (stop - area.left) * new_advance // old_advance for stop in self._layout.horizontal_tabs
        }
        self._active_x = self._grid_ceiling(self._active_x, area.left, new_advance)

    def _set_ibm_horizontal_pitch(self, tenths_cpi: int) -> None:
        if tenths_cpi <= 0:
            return
        self._layout.ibm_base_horizontal_advance = round(PRINT_UNITS_PER_INCH * 10 / tenths_cpi)
        self._apply_ibm_horizontal_advance()

    def _set_ibm_double_width(self, enabled: bool) -> None:
        if self._layout.ibm_double_width == enabled:
            return
        self._layout.ibm_double_width = enabled
        self._apply_ibm_horizontal_advance()

    def _apply_ibm_horizontal_advance(self) -> None:
        self._flush_pending_run()
        self._layout.horizontal_advance = self._layout.ibm_base_horizontal_advance * (
            2 if self._layout.ibm_double_width else 1
        )
        if self._active_x > self._layout.right_margin:
            self._active_x = self._layout.right_margin
            self._right_margin_flag = True

    def _set_ibm_line_spacing(self, units_216: int) -> None:
        if units_216 > 0:
            self._layout.vertical_advance = units_216 * (PRINT_UNITS_PER_INCH // 216)
            self._layout.vertical_grid_pending = False
        self._apply_ibm_perforation_skip()

    def _ibm_vertical_motion(self, units_216: int) -> None:
        """ESC J: feed paper, and begin a new line for CAN to cancel."""
        if units_216 > 0:
            target = self._active_y + units_216 * (PRINT_UNITS_PER_INCH // 216)
            if self._layout.no_forms or target < self._layout.bottom_margin:
                self._active_y = target
            else:
                self._form_feed()
        self._line_checkpoint = self._page_store.checkpoint()

    def _reset_ibm_tabs(self) -> None:
        area = self.page_geometry.printable_area
        capacity = area.width // self._layout.horizontal_advance + 1
        self._layout.horizontal_tabs = {
            area.left + (column - 1) * self._layout.horizontal_advance for column in range(9, capacity + 1, 8)
        }
        self._layout.vertical_tabs.clear()

    def _set_ibm_form_length_lines(self, lines: int) -> None:
        self._set_page_length(lines)
        self._apply_ibm_perforation_skip()

    def _set_ibm_form_length_inches(self, inches: int) -> None:
        if inches > 0:
            area = self.page_geometry.printable_area
            self._layout.no_forms = False
            self._layout.logical_page_bottom = area.top + min(inches * PRINT_UNITS_PER_INCH, area.height)
            self._layout.top_margin = area.top
            self._layout.bottom_margin = self._layout.logical_page_bottom
        self._apply_ibm_perforation_skip()

    def _set_ibm_top_of_form(self) -> None:
        area = self.page_geometry.printable_area
        form_length = max(self._layout.vertical_advance, self._layout.logical_page_bottom - self._layout.top_margin)
        self._layout.top_margin = min(max(self._active_y, area.top), area.bottom)
        self._layout.logical_page_bottom = min(self._layout.top_margin + form_length, area.bottom)
        self._apply_ibm_perforation_skip()

    def _apply_ibm_perforation_skip(self) -> None:
        if self._layout.no_forms:
            return
        skipped = self._layout.ibm_perforation_skip * self._layout.vertical_advance
        self._layout.bottom_margin = max(self._layout.top_margin, self._layout.logical_page_bottom - skipped)

    def _save_dec_layout(self) -> None:
        """Entering the IBM language: set the DEC layout aside whole and start from power-on."""
        self._dec_layout = self._layout
        self._layout = _Layout.power_on(self.page_geometry.printable_area, PrinterLanguage.IBM_PROPRINTER)
        self._reset_ibm_tabs()
        self._clamp_head()

    def _restore_dec_layout(self) -> None:
        """Leaving it: the DEC layout comes back; the IBM pitch does not, and the perforation skip stays."""
        if self._dec_layout is None:
            return
        self._layout = replace(
            self._dec_layout,
            ibm_base_horizontal_advance=PRINT_UNITS_PER_INCH // 10,
            ibm_double_width=False,
            ibm_perforation_skip=self._layout.ibm_perforation_skip,
        )
        self._dec_layout = None
        self._clamp_head()

    def _clamp_head(self) -> None:
        """Bring the print head inside the margins of a layout it was not set in."""
        layout = self._layout
        self._active_x = min(max(self._active_x, layout.left_margin), layout.right_margin)
        self._active_y = max(self._active_y, layout.top_margin)
        self._right_margin_flag = self._active_x >= layout.right_margin

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
        old_advance = self._layout.vertical_advance
        origin = self.page_geometry.printable_area.top
        self._layout.vertical_advance = new_advance
        self._layout.vertical_tabs = {
            origin + (stop - origin) * new_advance // old_advance for stop in self._layout.vertical_tabs
        }
        if not self._layout.no_forms:
            self._layout.top_margin = min(
                self._grid_ceiling(self._layout.top_margin, origin, new_advance),
                self._layout.logical_page_bottom,
            )
            self._layout.bottom_margin = min(
                self._grid_ceiling(self._layout.bottom_margin, origin, new_advance),
                self._layout.logical_page_bottom,
            )
            self._layout.vertical_grid_pending = True

    def _set_page_length(self, parameter: int) -> None:
        area = self.page_geometry.printable_area
        if parameter == 0:
            self._layout.no_forms = True
            self._layout.vertical_grid_pending = False
            return
        length = self._parameter_distance(parameter, horizontal=False)
        self._layout.no_forms = False
        self._layout.logical_page_bottom = area.top + min(length, area.height)
        self._layout.top_margin = area.top
        self._layout.bottom_margin = self._layout.logical_page_bottom

    def _set_horizontal_margins(self, left: int, right: int) -> None:
        area = self.page_geometry.printable_area
        new_left = self._layout.left_margin if left == 0 else self._parameter_position(left, horizontal=True)
        new_right = (
            self._layout.right_margin if right == 0 else (area.left + self._parameter_distance(right, horizontal=True))
        )
        new_right = min(new_right, area.right)
        if new_left > new_right or new_left > area.right:
            return
        self._layout.left_margin = new_left
        self._layout.right_margin = new_right
        if self._active_x < new_left:
            self._active_x = new_left
        elif self._active_x > new_right:
            self._active_x = new_right
            self._right_margin_flag = True

    def _set_vertical_margins(self, top: int, bottom: int) -> None:
        if self._layout.no_forms:
            return
        area = self.page_geometry.printable_area
        new_top = self._layout.top_margin if top == 0 else self._parameter_position(top, horizontal=False)
        new_bottom = (
            self._layout.bottom_margin
            if bottom == 0
            else (area.top + self._parameter_distance(bottom, horizontal=False))
        )
        new_bottom = min(new_bottom, self._layout.logical_page_bottom)
        if new_top > new_bottom or new_top > self._layout.logical_page_bottom:
            return
        self._layout.top_margin = new_top
        self._layout.bottom_margin = new_bottom
        self._layout.vertical_grid_pending = False
        if self._active_y < new_top:
            self._active_y = new_top
        elif self._active_y > self._last_vertical_position():
            self._form_feed()

    def _horizontal_absolute(self, parameter: int) -> None:
        target = self._parameter_position(max(1, parameter), horizontal=True)
        target = max(target, self._layout.left_margin)
        if target > self._layout.right_margin:
            target = self._layout.right_margin
            self._right_margin_flag = True
        self._record_lined_motion(self._active_x, target)
        self._active_x = target
        if target < self._layout.right_margin:
            self._right_margin_flag = False

    def _horizontal_relative(self, parameter: int) -> None:
        if self._right_margin_flag:
            return
        target = self._active_x + self._parameter_distance(max(1, parameter), horizontal=True)
        if target > self._layout.right_margin:
            target = self._layout.right_margin
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
                    self._active_y + self._layout.vertical_advance,
                ),
                self.state,
            )
        )

    def _vertical_absolute(self, parameter: int) -> None:
        if self._layout.no_forms:
            self._advance_line(home=False)
            return
        self._align_vertical_grid()
        target = self._parameter_position(max(1, parameter), horizontal=False)
        if target < self._active_y:
            return
        self._active_y = min(max(target, self._layout.top_margin), self._last_vertical_position())

    def _vertical_relative(self, parameter: int) -> None:
        self._align_vertical_grid()
        count = max(1, parameter)
        if self._layout.no_forms:
            count = min(count, 255)
        target = self._active_y + self._parameter_distance(count, horizontal=False)
        self._active_y = target if self._layout.no_forms else min(target, self._last_vertical_position())

    def _set_tab_parameters(self, table: set[int], parameters: tuple[int, ...], *, horizontal: bool) -> None:
        for parameter in parameters:
            if parameter > 0:
                table.add(self._parameter_position(parameter, horizontal=horizontal))

    def _clear_tabs(self, parameters: tuple[int, ...]) -> None:
        for parameter in parameters:
            if parameter == 0:
                self._layout.horizontal_tabs.discard(self._active_x)
            elif parameter == 1:
                self._align_vertical_grid()
                self._layout.vertical_tabs.discard(self._active_y)
            elif parameter in (2, 3):
                self._layout.horizontal_tabs.clear()
            elif parameter == 4:
                self._layout.vertical_tabs.clear()

    def _parameter_distance(self, parameter: int, *, horizontal: bool) -> int:
        if self.state.position_unit_mode:
            return parameter * (PRINT_UNITS_PER_INCH // 720)
        return parameter * (self._layout.horizontal_advance if horizontal else self._layout.vertical_advance)

    def _parameter_position(self, parameter: int, *, horizontal: bool) -> int:
        area = self.page_geometry.printable_area
        origin = area.left if horizontal else area.top
        return origin + self._parameter_distance(max(1, parameter) - 1, horizontal=horizontal)

    def _align_vertical_grid(self) -> None:
        if not self._layout.vertical_grid_pending:
            return
        self._active_y = self._grid_ceiling(
            self._active_y,
            self.page_geometry.printable_area.top,
            self._layout.vertical_advance,
        )
        self._layout.vertical_grid_pending = False

    def _last_vertical_position(self) -> int:
        if self._layout.bottom_margin - self._layout.top_margin < self._layout.vertical_advance:
            return self._layout.top_margin
        return self._layout.bottom_margin - self._layout.vertical_advance

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
            available = (self._layout.right_margin - self._active_x) // self._layout.horizontal_advance
            if available <= 0:
                self._right_margin_flag = True
                return
            end = min(len(text), offset + available)
            segment = text[offset:end]
            advance = len(segment) * self._layout.horizontal_advance
            token = PrinterControlToken(
                PrinterRect(
                    self._active_x,
                    self._active_y,
                    self._active_x + advance,
                    self._active_y + self._layout.vertical_advance,
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
        advance = len(data) * self._layout.horizontal_advance
        run = PrinterTextRun(
            PrinterRect(
                x,
                y,
                x + advance,
                y + self._layout.vertical_advance,
            ),
            data,
            data.decode("ascii") if ascii_run else None,
            advance,
            state,
        )
        self._page_store.append(run, marks=marks)

    def write_bytes(self, data: bytes) -> int:
        if self.closed:
            raise ValueError("printer is closed")
        if self.trace is not None:
            self.trace += data
        self._language_engine.feed(data)
        return len(data)

    def reset(self) -> None:
        """Restore the physical printer's power-on language state."""
        self._language_engine.reset()
        self._unsolicited_reports = PrinterUnsolicitedReports.DISABLED
