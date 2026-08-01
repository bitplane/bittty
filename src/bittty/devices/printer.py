"""Auxiliary-printer device, Media Copy semantics, and host-data routing."""

from __future__ import annotations

import codecs
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from ..connections import PrinterConnection, PrinterPort, PrinterStatus
from ..operations import Operation
from ..printer_config import (
    PrintedDataType,
    PrinterConfiguration,
    PrinterFlowControl,
    PrinterFlowThreshold,
    PrinterParity,
    PrinterPortSelection,
    PrinterType,
    ProPrinterCodePage,
)
from .base import Device

if TYPE_CHECKING:
    from .board import Board


_ENTRY_BYTES = (b"\x1b[5i", b"\x9b5i")
_EXIT_BYTES = (b"\x1b[4i", b"\x9b4i")
_ENTRY_TEXT = ("\x1b[5i", "\x9b5i")
_EXIT_TEXT = ("\x1b[4i", "\x9b4i")
_FLOW_CONTROL_DELETE = b"\x00\x11\x13"
_BAUD_BY_SELECTOR = {
    0: 4800,
    1: 300,
    2: 600,
    3: 1200,
    4: 2400,
    5: 4800,
    6: 9600,
    7: 19200,
    8: 38400,
    9: 57600,
    10: 76800,
    11: 115200,
}
_SELECTOR_BY_BAUD = {baud: selector for selector, baud in _BAUD_BY_SELECTOR.items() if selector != 0}


def _first_pattern(data, patterns):
    found = None
    for pattern in patterns:
        index = data.find(pattern)
        if index >= 0 and (found is None or index < found[0]):
            found = (index, pattern)
    return found


def _partial_suffix_length(data, patterns) -> int:
    limit = min(len(data), max(map(len, patterns)) - 1)
    for length in range(limit, 0, -1):
        tail = data[-length:]
        if any(pattern.startswith(tail) for pattern in patterns):
            return length
    return 0


class _TextPrinterAdapter:
    """Best-effort compatibility for the historical write(str)/callable API."""

    status = PrinterStatus.READY
    closed = False

    def __init__(self, sink, encoding: str, errors: str) -> None:
        self.sink = sink
        self._decoder = codecs.getincrementaldecoder(encoding)(errors=errors)

    def write_bytes(self, data: bytes):
        text = self._decoder.decode(data, final=False)
        if not text:
            return 0
        writer = self.sink.write if hasattr(self.sink, "write") else self.sink
        return writer(text)

    def flush(self) -> None:
        flusher = getattr(self.sink, "flush", None)
        if callable(flusher):
            flusher()


class PrinterDevice(Device):
    """Own printer modes and the byte-oriented auxiliary port."""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.sink = None
        self.encoding = "utf-8"
        self.errors = "replace"
        self.port = PrinterPort(on_data=self.receive_bytes)
        self.controller_mode = False
        self.auto_print = False
        self.printer_to_host = False
        self.print_form_feed = False
        self.print_extent = False
        self.configuration = PrinterConfiguration()
        self._byte_pending = b""
        self._text_pending = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.handlers = {
            "MC": self.media_copy,
            "DECMC": self.dec_media_copy,
            "DSR_PRINTER": self.report_status,
            "DECSPRTT": self.set_printer_type,
            "DECSDPT": self.set_printed_data_type,
            "DECSPPCS": self.set_code_page,
            "DECSCP": self.set_port,
            "DECSCS": self.set_speed,
            "DECSFC": self.set_flow_control,
            "DECSPP": self.set_port_parameters,
        }

    @property
    def capabilities(self):
        return self.board.model.printer_capabilities

    def attach(self, sink, *, encoding: str = "utf-8", errors: str = "replace") -> None:
        """Attach a printer connection or a legacy callable/write(str) sink."""
        self.sink = sink
        self.encoding = encoding
        self.errors = errors
        if callable(getattr(sink, "write_bytes", None)):
            connection = sink
        else:
            connection = _TextPrinterAdapter(sink, encoding, errors)
        self.port.attach(connection)
        self._configure_adapter()

    def connect(
        self,
        connection: PrinterConnection,
        *,
        encoding: str = "utf-8",
        errors: str = "replace",
    ) -> None:
        """Attach a duplex byte connection and start its inbound pump."""
        self.sink = connection
        self.encoding = encoding
        self.errors = errors
        self.port.connect(connection)
        self._configure_adapter()

    def detach(self) -> None:
        self.port.disconnect()
        self.sink = None

    @property
    def status(self) -> PrinterStatus:
        if not self.port.connected:
            return self.capabilities.disconnected_status
        return self.port.status

    def emit_bytes(self, data: bytes, *, flush: bool = False):
        return self.port.write_bytes(data, flush=flush)

    def emit(self, text: str) -> None:
        """Compatibility spelling for composed printer text."""
        self.emit_text(text)

    def emit_text(self, text: str, *, flush: bool = False) -> None:
        self.emit_bytes(text.encode(self.encoding, errors=self.errors), flush=flush)

    def receive_bytes(self, data: bytes) -> None:
        """Receive printer-originated data and optionally forward it to the host."""
        if self.capabilities.media_copy and self.printer_to_host:
            filtered = self._filter_printer_data(data)
            if filtered:
                self.board.host.write_bytes(filtered)

    def media_copy(self, operation: Operation) -> None:
        """MC (CSI Ps i) — ANSI media-copy and controller controls."""
        if not self.capabilities.media_copy:
            return
        ps = operation.args[0]
        if ps == 0:
            self.print_screen(respect_extent=True)
        elif ps == 2:
            self.send_screen_to_host()
        elif ps == 4:
            self.controller_mode = False
        elif ps == 5:
            self.auto_print = False
            self.controller_mode = True
        elif ps == 6:
            self.printer_to_host = True
        elif ps == 7:
            self.printer_to_host = False

    def dec_media_copy(self, operation: Operation) -> None:
        """DEC MC (CSI ? Ps i) — composed output and printer input controls."""
        if not self.capabilities.media_copy:
            return
        ps = operation.args[0]
        if ps == 1:
            self.print_line(self.board.cursor.y)
        elif ps == 4:
            self.auto_print = False
        elif ps == 5:
            self.auto_print = True
        elif ps == 8:
            self.printer_to_host = False
        elif ps == 9:
            self.printer_to_host = True
        elif ps in (10, 11):
            self.print_screen()

    def report_status(self, operation: Operation) -> None:
        if not self.capabilities.media_copy:
            return
        self.board.host.write(f"\x1b[?{int(self.status)}n", flush=True)

    @staticmethod
    def _at(params: tuple[int | None, ...], index: int, default: int) -> int:
        value = params[index] if len(params) > index else None
        return default if value is None else value

    def _replace_configuration(self, **changes) -> None:
        if not self.capabilities.configuration:
            return
        configuration = replace(self.configuration, **changes)
        if configuration == self.configuration:
            return
        self.configuration = configuration
        self._configure_adapter()

    def _configure_adapter(self) -> None:
        if self.capabilities.configuration and self.port.connected:
            self.port.configure(self.configuration)

    def set_ignore_null(self, enabled: bool) -> None:
        self._replace_configuration(ignore_null=enabled)

    def set_printer_type(self, operation: Operation) -> None:
        params = operation.args[0]
        selector = self._at(params, 0, 0) or 1
        try:
            value = PrinterType(selector)
        except ValueError:
            return
        self._replace_configuration(printer_type=value)

    def set_printed_data_type(self, operation: Operation) -> None:
        params = operation.args[0]
        selector = self._at(params, 0, 0) or 1
        try:
            value = PrintedDataType(selector)
        except ValueError:
            return
        self._replace_configuration(printed_data_type=value)

    def set_code_page(self, operation: Operation) -> None:
        params = operation.args[0]
        try:
            value = ProPrinterCodePage(self._at(params, 0, 437))
        except ValueError:
            return
        self._replace_configuration(code_page=value)

    def set_port(self, operation: Operation) -> None:
        params = operation.args[0]
        if self._at(params, 1, 1) != 1:
            return
        try:
            value = PrinterPortSelection(self._at(params, 0, 1))
        except ValueError:
            return
        self._replace_configuration(port=value)

    def set_speed(self, operation: Operation) -> None:
        params = operation.args[0]
        if self._at(params, 0, 0) != 3:
            return
        baud_rate = _BAUD_BY_SELECTOR.get(self._at(params, 1, 0))
        if baud_rate is not None:
            self._replace_configuration(baud_rate=baud_rate)

    def set_flow_control(self, operation: Operation) -> None:
        params = operation.args[0]
        if self._at(params, 0, 0) != 2:
            return
        direction = self._at(params, 1, 1)
        try:
            flow = PrinterFlowControl(self._at(params, 2, 1))
            threshold = PrinterFlowThreshold(self._at(params, 3, 1))
        except ValueError:
            return
        if direction not in (1, 2, 3):
            return
        changes = {}
        if direction in (1, 3):
            changes["transmit_flow_control"] = flow
        if direction in (2, 3):
            changes["receive_flow_control"] = flow
        # VT510 printer ports always use the low threshold.
        if threshold is PrinterFlowThreshold.LOW:
            changes["flow_threshold"] = threshold
        self._replace_configuration(**changes)

    def set_port_parameters(self, operation: Operation) -> None:
        params = operation.args[0]
        if self._at(params, 0, 0) != 2:
            return
        bits_selector = self._at(params, 1, 1)
        stop_selector = self._at(params, 3, 1)
        if bits_selector not in (1, 2) or stop_selector not in (1, 2):
            return
        try:
            parity = PrinterParity(self._at(params, 2, 1))
        except ValueError:
            return
        self._replace_configuration(
            data_bits=8 if bits_selector == 1 else 7,
            parity=parity,
            stop_bits=stop_selector,
        )

    def status_strings(self, request: str) -> tuple[str, ...] | None:
        """Return restorable VT510 printer-setting strings for DECRQSS."""
        if not self.capabilities.configuration:
            return None
        config = self.configuration
        if request == "$s":
            return (f"{int(config.printer_type)}$s",)
        if request == ")p":
            return (f"{int(config.printed_data_type)})p",)
        if request == "*p":
            return (f"{int(config.code_page)}*p",)
        if request == "*r":
            return (f"3;{_SELECTOR_BY_BAUD[config.baud_rate]}*r",)
        if request == "*u":
            return (f"{int(config.port)};1*u",)
        if request == "*s":
            return (
                f"2;1;{int(config.transmit_flow_control)};1*s",
                f"2;2;{int(config.receive_flow_control)};1*s",
            )
        if request == "+w":
            bits = 1 if config.data_bits == 8 else 2
            return (f"2;{bits};{int(config.parity)};{config.stop_bits}+w",)
        return None

    def _screen_text(self, *, respect_extent: bool = False) -> str:
        page = self.board.blitter.current_page
        if respect_extent and not self.print_extent:
            top = self.board.blitter.scroll_top
            bottom = self.board.blitter.scroll_bottom
        else:
            top = 0
            bottom = self.board.height - 1
        lines = [page.get_line_text(y).rstrip() for y in range(top, bottom + 1)]
        return "\r\n".join(lines) + "\r\n"

    def print_screen(self, *, respect_extent: bool = False) -> None:
        """Send one composed page, optionally applying DECPEX to ANSI MC 0."""
        text = self._screen_text(respect_extent=respect_extent)
        if self.print_form_feed:
            text += "\f"
        self.emit_text(text)

    def send_screen_to_host(self) -> None:
        """MC 2 — send the active screen's composed data toward the host."""
        self.board.host.write_bytes(
            self._screen_text().encode(self.encoding, errors=self.errors),
            flush=True,
        )

    def print_line(self, y: int) -> None:
        """Print a composed cursor line."""
        text = self.board.blitter.current_page.get_line_text(y).rstrip()
        self.emit_text(text + "\r\n")

    def auto_print_line(self, y: int, trigger: str) -> None:
        """Print the line being left, ending in CR and the triggering control."""
        text = self.board.blitter.current_page.get_line_text(y).rstrip()
        self.emit_text(text + "\r" + trigger)

    def feed_host_data(self, data: bytes | str, normal_sink: Callable[[str], None]) -> None:
        """Route host output around the parser while printer-controller mode is active."""
        if not self.capabilities.media_copy:
            if isinstance(data, bytes):
                self._feed_normal_bytes(data, normal_sink)
            elif data:
                normal_sink(data)
            return
        if isinstance(data, bytes):
            self._feed_host_bytes(data, normal_sink)
        else:
            self._feed_host_text(data, normal_sink)

    def _feed_normal_bytes(self, data: bytes, normal_sink: Callable[[str], None]) -> None:
        if data:
            text = self._decoder.decode(data, final=False)
            if text:
                normal_sink(text)

    @staticmethod
    def _control_text(pattern: bytes) -> str:
        return pattern.decode("latin-1") if pattern.startswith(b"\x9b") else pattern.decode("ascii")

    def _feed_host_bytes(self, data: bytes, normal_sink: Callable[[str], None]) -> None:
        data = self._byte_pending + data
        self._byte_pending = b""
        while data:
            if self.controller_mode:
                patterns = _ENTRY_BYTES + _EXIT_BYTES
                found = _first_pattern(data, patterns)
                if found is None:
                    keep = _partial_suffix_length(data, patterns)
                    body = data[:-keep] if keep else data
                    if body:
                        self.emit_bytes(self._filter_printer_data(body))
                    self._byte_pending = data[-keep:] if keep else b""
                    return
                index, pattern = found
                if index:
                    self.emit_bytes(self._filter_printer_data(data[:index]))
                data = data[index + len(pattern) :]
                if pattern in _EXIT_BYTES:
                    normal_sink(self._control_text(pattern))
                # Repeated controller-entry sequences are consumed, not printed.
                continue

            found = _first_pattern(data, _ENTRY_BYTES)
            if found is None:
                keep = _partial_suffix_length(data, _ENTRY_BYTES)
                body = data[:-keep] if keep else data
                self._feed_normal_bytes(body, normal_sink)
                self._byte_pending = data[-keep:] if keep else b""
                return
            index, pattern = found
            self._feed_normal_bytes(data[:index], normal_sink)
            normal_sink(self._control_text(pattern))
            data = data[index + len(pattern) :]

    def _feed_host_text(self, data: str, normal_sink: Callable[[str], None]) -> None:
        data = self._text_pending + data
        self._text_pending = ""
        while data:
            if self.controller_mode:
                patterns = _ENTRY_TEXT + _EXIT_TEXT
                found = _first_pattern(data, patterns)
                if found is None:
                    keep = _partial_suffix_length(data, patterns)
                    body = data[:-keep] if keep else data
                    if body:
                        filtered = self._filter_printer_text(body)
                        self.emit_text(filtered)
                    self._text_pending = data[-keep:] if keep else ""
                    return
                index, pattern = found
                if index:
                    filtered = self._filter_printer_text(data[:index])
                    self.emit_text(filtered)
                data = data[index + len(pattern) :]
                if pattern in _EXIT_TEXT:
                    normal_sink(pattern)
                continue

            found = _first_pattern(data, _ENTRY_TEXT)
            if found is None:
                keep = _partial_suffix_length(data, _ENTRY_TEXT)
                body = data[:-keep] if keep else data
                if body:
                    normal_sink(body)
                self._text_pending = data[-keep:] if keep else ""
                return
            index, pattern = found
            if index:
                normal_sink(data[:index])
            normal_sink(pattern)
            data = data[index + len(pattern) :]

    def _filter_printer_data(self, data: bytes) -> bytes:
        if not self.capabilities.configuration:
            return data.translate(None, _FLOW_CONTROL_DELETE)
        delete = bytearray()
        if self.configuration.ignore_null:
            delete.append(0)
        software = {PrinterFlowControl.XON_XOFF, PrinterFlowControl.BOTH}
        if self.configuration.transmit_flow_control in software or self.configuration.receive_flow_control in software:
            delete.extend((0x11, 0x13))
        return data.translate(None, bytes(delete)) if delete else data

    def _filter_printer_text(self, data: str) -> str:
        if not self.capabilities.configuration:
            return data.translate({0: None, 0x11: None, 0x13: None})
        table: dict[int, None] = {}
        if self.configuration.ignore_null:
            table[0] = None
        software = {PrinterFlowControl.XON_XOFF, PrinterFlowControl.BOTH}
        if self.configuration.transmit_flow_control in software or self.configuration.receive_flow_control in software:
            table[0x11] = None
            table[0x13] = None
        return data.translate(table) if table else data

    def reset(self, hard: bool = True) -> None:
        """Reset volatile modes while leaving the physical printer connected."""
        self.controller_mode = False
        self.auto_print = False
        self.printer_to_host = False
        self.print_form_feed = False
        self.print_extent = False
        self._replace_configuration(ignore_null=False)
