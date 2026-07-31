"""Streaming state for the printer languages understood by virtual printers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PrinterLanguage(Enum):
    """Printer command language currently selected by a virtual printer."""

    DEC_PPL = "dec-ppl"
    IBM_PROPRINTER = "ibm-proprinter"


class PrintDirection(Enum):
    """DEC PPL print-direction mode."""

    BIDIRECTIONAL = "bidirectional"
    UNIDIRECTIONAL = "unidirectional"


@dataclass(frozen=True)
class VirtualPrinterState:
    """Observable language state of a virtual printer."""

    language: PrinterLanguage
    direction: PrintDirection


_ESC = 0x1B
_CAN = 0x18
_SUB = 0x1A
_C1_CSI = 0x9B
_C1_ST = 0x9C
_C1_STRINGS = frozenset((0x90, 0x98, 0x9D, 0x9E, 0x9F))
_DEC_SPECIAL_BYTES = (b"\x1b", b"\x90", b"\x98", b"\x9b", b"\x9d", b"\x9e", b"\x9f")
_MAX_CSI = 128


class _PrinterLanguageEngine:
    """Incremental DEC PPL/IBM protocol-selection parser.

    This deliberately models only language selection, print direction, and
    resets. Ordinary print data remains on a fast path and is not interpreted.
    """

    def __init__(
        self,
        initial_language: PrinterLanguage,
        *,
        supports_proprinter_switching: bool,
    ) -> None:
        self._initial_language = initial_language
        self._supports_proprinter_switching = supports_proprinter_switching
        self._language = initial_language
        self._direction = PrintDirection.BIDIRECTIONAL
        self._dec_state = "ground"
        self._dec_string_is_osc = False
        self._csi = bytearray()
        self._ibm_pending = bytearray()

    @property
    def state(self) -> VirtualPrinterState:
        return VirtualPrinterState(self._language, self._direction)

    def reset(self) -> None:
        """Apply a power-on reset and discard any partial input sequence."""
        self._language = self._initial_language
        self._direction = PrintDirection.BIDIRECTIONAL
        self._dec_state = "ground"
        self._dec_string_is_osc = False
        self._csi.clear()
        self._ibm_pending.clear()

    def feed(self, data: bytes) -> None:
        """Consume one arbitrary stream fragment."""
        offset = 0
        size = len(data)
        while offset < size:
            if self._language is PrinterLanguage.IBM_PROPRINTER:
                if not self._supports_proprinter_switching:
                    return
                offset = self._feed_ibm(data, offset)
            else:
                offset = self._feed_dec(data, offset)

    def _feed_dec(self, data: bytes, offset: int) -> int:
        size = len(data)
        while offset < size and self._language is PrinterLanguage.DEC_PPL:
            byte = data[offset]
            offset += 1

            if self._dec_state == "ground":
                if byte == _ESC:
                    self._dec_state = "escape"
                elif byte == _C1_CSI:
                    self._begin_csi()
                elif byte in _C1_STRINGS:
                    self._begin_string(is_osc=byte == 0x9D)
                else:
                    # Most printer output is ordinary text. Scan it in C rather
                    # than returning to Python for every byte.
                    next_special = size
                    for marker in _DEC_SPECIAL_BYTES:
                        found = data.find(marker, offset)
                        if found != -1 and found < next_special:
                            next_special = found
                    offset = next_special
            elif self._dec_state == "escape":
                if byte == ord("["):
                    self._begin_csi()
                elif byte in (ord("P"), ord("X"), ord("]"), ord("^"), ord("_")):
                    self._begin_string(is_osc=byte == ord("]"))
                elif byte == ord("%"):
                    self._dec_state = "percent"
                elif byte == ord("c"):
                    self._reset_dec_modes()
                    self._dec_state = "ground"
                elif byte == _ESC:
                    pass
                else:
                    self._dec_state = "ground"
            elif self._dec_state == "percent":
                if byte == ord("=") and self._supports_proprinter_switching:
                    self._language = PrinterLanguage.IBM_PROPRINTER
                    self._dec_state = "ground"
                elif byte == _ESC:
                    self._dec_state = "escape"
                else:
                    self._dec_state = "ground"
            elif self._dec_state == "csi":
                self._consume_csi(byte)
            elif self._dec_state == "string":
                if byte == _C1_ST or byte in (_CAN, _SUB) or (byte == 0x07 and self._dec_string_is_osc):
                    self._dec_state = "ground"
                elif byte == _ESC:
                    self._dec_state = "string_escape"
            else:  # string_escape
                if byte in (ord("\\"), _C1_ST, _CAN, _SUB) or byte == 0x07 and self._dec_string_is_osc:
                    self._dec_state = "ground"
                elif byte != _ESC:
                    self._dec_state = "string"
        return offset

    def _begin_csi(self) -> None:
        self._csi.clear()
        self._dec_state = "csi"

    def _begin_string(self, *, is_osc: bool) -> None:
        self._dec_string_is_osc = is_osc
        self._dec_state = "string"

    def _consume_csi(self, byte: int) -> None:
        if byte in (_CAN, _SUB):
            self._csi.clear()
            self._dec_state = "ground"
            return
        if byte == _ESC:
            self._csi.clear()
            self._dec_state = "escape"
            return
        if 0x40 <= byte <= 0x7E:
            body = bytes(self._csi)
            self._csi.clear()
            self._dec_state = "ground"
            self._dispatch_dec_csi(body, byte)
            return
        if len(self._csi) >= _MAX_CSI:
            self._csi.clear()
            self._dec_state = "ground"
            return
        self._csi.append(byte)

    def _dispatch_dec_csi(self, body: bytes, final: int) -> None:
        if final in (ord("h"), ord("l")) and body.startswith(b"?"):
            parameters = self._numeric_parameters(body[1:])
            if parameters is None:
                return
            enabled = final == ord("h")
            for parameter in parameters:
                if parameter == 41:
                    self._direction = PrintDirection.UNIDIRECTIONAL if enabled else PrintDirection.BIDIRECTIONAL
                elif parameter == 58 and enabled and self._supports_proprinter_switching:
                    self._language = PrinterLanguage.IBM_PROPRINTER
                    return
            return

        if final == ord("p") and body.endswith(b"!"):
            parameters = self._numeric_parameters(body[:-1])
            if parameters is not None:
                self._reset_dec_modes()

    @staticmethod
    def _numeric_parameters(data: bytes) -> list[int] | None:
        if any(byte not in b"0123456789;" for byte in data):
            return None
        if not data:
            return []
        return [int(part) for part in data.split(b";") if part]

    def _reset_dec_modes(self) -> None:
        self._direction = PrintDirection.BIDIRECTIONAL

    def _feed_ibm(self, data: bytes, offset: int) -> int:
        patterns = (b"\x1b%@", b"\x1b[?58l", b"\x1b[!p")
        size = len(data)
        while offset < size and self._language is PrinterLanguage.IBM_PROPRINTER:
            if not self._ibm_pending:
                found = data.find(b"\x1b", offset)
                if found == -1:
                    return size
                offset = found

            self._ibm_pending.append(data[offset])
            offset += 1
            pending = bytes(self._ibm_pending)
            candidates = tuple(pattern for pattern in patterns if pattern.startswith(pending))
            if not candidates:
                keep_escape = pending.endswith(b"\x1b")
                self._ibm_pending.clear()
                if keep_escape:
                    self._ibm_pending.append(_ESC)
                continue
            if pending in candidates:
                self._ibm_pending.clear()
                if pending != b"\x1b[!p":
                    self._language = PrinterLanguage.DEC_PPL
                    self._dec_state = "ground"
        return offset
