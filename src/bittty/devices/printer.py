"""Auxiliary-printer device, Media Copy semantics, and host-data routing."""

from __future__ import annotations

import codecs
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from ..connections import PrinterConnection, PrinterPort, PrinterStatus
from ..operations import Operation
from ..connections.printer_config import (
    PrintedDataType,
    PrinterConfiguration,
    PrinterType,
    ProPrinterCodePage,
)
from ..connections.serial_line import FlowControl
from .base import Device

if TYPE_CHECKING:
    from .board import Board


# The host line is UTF-8: an eight-bit CSI arrives as U+009B (C2 9B), never as a bare
# 0x9B, which is a continuation byte inside characters such as Û (C3 9B).
_ENTRY_BYTES = ("\x1b[5i".encode(), "\x9b5i".encode())
_EXIT_BYTES = ("\x1b[4i".encode(), "\x9b4i".encode())
_FLOW_CONTROL_DELETE = b"\x00\x11\x13"


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


class PrinterDevice(Device):
    """Own printer modes and the byte-oriented auxiliary port."""

    def __init__(self, board: Board) -> None:
        self.board = board
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
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.handlers = {
            "MC": self.media_copy,
            "DECMC": self.dec_media_copy,
            "DSR_PRINTER": self.report_status,
            "DECSPRTT": self.set_printer_type,
            "DECSDPT": self.set_printed_data_type,
            "DECSPPCS": self.set_code_page,
        }

    @property
    def capabilities(self):
        return self.board.model.printer_capabilities

    def attach(self, connection: PrinterConnection, *, encoding: str = "utf-8", errors: str = "replace") -> None:
        """Plug in a printer cable, transmit side only; composed text is encoded as `encoding`."""
        self.port.attach(connection)
        self._plugged(encoding, errors)

    def connect(self, connection: PrinterConnection, *, encoding: str = "utf-8", errors: str = "replace") -> None:
        """Plug in a duplex printer cable and start its inbound pump."""
        self.port.connect(connection)
        self._plugged(encoding, errors)

    def _plugged(self, encoding: str, errors: str) -> None:
        self.encoding = encoding
        self.errors = errors
        self._configure_adapter()

    def detach(self) -> None:
        self.port.disconnect()

    @property
    def status(self) -> PrinterStatus:
        if not self.port.connected:
            return self.capabilities.disconnected_status
        return self.port.status

    def emit_bytes(self, data: bytes, *, flush: bool = False):
        return self.port.write_bytes(data, flush=flush)

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

    def configure(self, **changes) -> None:
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
        self.configure(ignore_null=enabled)

    def set_printer_type(self, operation: Operation) -> None:
        params = operation.args[0]
        selector = self._at(params, 0, 0) or 1
        try:
            value = PrinterType(selector)
        except ValueError:
            return
        self.configure(printer_type=value)

    def set_printed_data_type(self, operation: Operation) -> None:
        params = operation.args[0]
        selector = self._at(params, 0, 0) or 1
        try:
            value = PrintedDataType(selector)
        except ValueError:
            return
        self.configure(printed_data_type=value)

    def set_code_page(self, operation: Operation) -> None:
        params = operation.args[0]
        try:
            value = ProPrinterCodePage(self._at(params, 0, 437))
        except ValueError:
            return
        self.configure(code_page=value)

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
        return None

    def _screen_text(self, *, respect_extent: bool = False) -> str:
        page = self.board.blitter.current_page
        if respect_extent and not self.print_extent:
            top = self.board.blitter.scroll_top
            bottom = self.board.blitter.scroll_bottom
        else:
            top = 0
            bottom = page.height - 1
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

    def feed_host_data(self, data: bytes, normal_sink: Callable[[str], None]) -> None:
        """Decode host output for the parser, routed around it while printer-controller mode is active."""
        if self.capabilities.media_copy:
            self._feed_host_bytes(data, normal_sink)
        else:
            self._feed_normal_bytes(data, normal_sink)

    def _feed_normal_bytes(self, data: bytes, normal_sink: Callable[[str], None]) -> None:
        if data:
            text = self._decoder.decode(data, final=False)
            if text:
                normal_sink(text)

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
                    normal_sink(pattern.decode())
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
            normal_sink(pattern.decode())
            data = data[index + len(pattern) :]

    def _filter_printer_data(self, data: bytes) -> bytes:
        if not self.capabilities.configuration:
            return data.translate(None, _FLOW_CONTROL_DELETE)
        delete = bytearray()
        if self.configuration.ignore_null:
            delete.append(0)
        software = {FlowControl.XON_XOFF, FlowControl.BOTH}
        if self.configuration.transmit_flow_control in software or self.configuration.receive_flow_control in software:
            delete.extend((0x11, 0x13))
        return data.translate(None, bytes(delete)) if delete else data

    def reset(self, hard: bool = True) -> None:
        """Reset volatile modes while leaving the physical printer connected."""
        self.controller_mode = False
        self.auto_print = False
        self.printer_to_host = False
        self.print_form_feed = False
        self.print_extent = False
        self.configure(ignore_null=False)
