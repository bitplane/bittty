"""Streaming state for the printer languages understood by virtual printers."""

from __future__ import annotations

from collections.abc import Callable
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
    proportional_spacing: bool = False
    pitch_from_font: bool = False
    carriage_return_new_line: bool = False
    autowrap: bool = True
    control_representation: bool = False
    line_feed_new_line: bool = False


_ESC = 0x1B
_CAN = 0x18
_SUB = 0x1A
_C1_CSI = 0x9B
_C1_ST = 0x9C
_C1_STRINGS = frozenset((0x90, 0x98, 0x9D, 0x9E, 0x9F))
_BS = 0x08
_HT = 0x09
_LF = 0x0A
_VT = 0x0B
_FF = 0x0C
_CR = 0x0D
_NEL = 0x85
_BASIC_CONTROLS = frozenset((_BS, _HT, _LF, _VT, _FF, _CR))
_DEC_SPECIAL_BYTES = (
    b"\x08",
    b"\x09",
    b"\x0a",
    b"\x0b",
    b"\x0c",
    b"\x0d",
    b"\x1b",
    b"\x85",
    b"\x90",
    b"\x98",
    b"\x9b",
    b"\x9d",
    b"\x9e",
    b"\x9f",
)
_NON_PRINTABLE_BYTES = bytes(range(0x20)) + b"\x7f" + bytes(range(0x80, 0xA0))
_MAX_CSI = 128
_C0_NAMES = (
    "NUL",
    "SOH",
    "STX",
    "ETX",
    "EOT",
    "ENQ",
    "ACK",
    "BEL",
    "BS",
    "HT",
    "LF",
    "VT",
    "FF",
    "CR",
    "SO",
    "SI",
    "DLE",
    "DC1",
    "DC2",
    "DC3",
    "DC4",
    "NAK",
    "SYN",
    "ETB",
    "CAN",
    "EM",
    "SUB",
    "ESC",
    "FS",
    "GS",
    "RS",
    "US",
)
_C1_NAMES = (
    None,
    None,
    "BPH",
    "NBH",
    "IND",
    "NEL",
    "SSA",
    "ESA",
    "HTS",
    "HTJ",
    "VTS",
    "PLD",
    "PLU",
    "RI",
    "SS2",
    "SS3",
    "DCS",
    "PU1",
    "PU2",
    "STS",
    "CCH",
    "MW",
    "SPA",
    "EPA",
    "SOS",
    None,
    "SCI",
    "CSI",
    "ST",
    "OSC",
    "PM",
    "APC",
)


class _PrinterLanguageEngine:
    """Incremental DEC PPL/IBM protocol-selection parser.

    This models retained language modes and resets. Ordinary DEC PPL print data
    remains on a batched fast path to an optional page-assembly sink.
    """

    def __init__(
        self,
        initial_language: PrinterLanguage,
        *,
        supports_proprinter_switching: bool,
        on_printable: Callable[[bytes], None] | None = None,
        on_control: Callable[[int], None] | None = None,
        on_crm_token: Callable[[bytes, str], None] | None = None,
    ) -> None:
        self._initial_language = initial_language
        self._supports_proprinter_switching = supports_proprinter_switching
        self._on_printable = on_printable
        self._on_control = on_control
        self._on_crm_token = on_crm_token
        self._language = initial_language
        self._direction = PrintDirection.BIDIRECTIONAL
        self._proportional_spacing = False
        self._pitch_from_font = False
        self._carriage_return_new_line = False
        self._autowrap = True
        self._control_representation = False
        self._line_feed_new_line = False
        self._dec_state = "ground"
        self._dec_string_is_osc = False
        self._csi = bytearray()
        self._crm_pending = bytearray()
        self._ibm_pending = bytearray()

    @property
    def state(self) -> VirtualPrinterState:
        return VirtualPrinterState(
            self._language,
            self._direction,
            proportional_spacing=self._proportional_spacing,
            pitch_from_font=self._pitch_from_font,
            carriage_return_new_line=self._carriage_return_new_line,
            autowrap=self._autowrap,
            control_representation=self._control_representation,
            line_feed_new_line=self._line_feed_new_line,
        )

    def reset(self) -> None:
        """Apply a power-on reset and discard any partial input sequence."""
        self._language = self._initial_language
        self._reset_dec_modes()
        self._dec_state = "ground"
        self._dec_string_is_osc = False
        self._csi.clear()
        self._crm_pending.clear()
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
            elif self._control_representation:
                offset = self._feed_crm(data, offset)
            else:
                offset = self._feed_dec(data, offset)

    def _feed_dec(self, data: bytes, offset: int) -> int:
        size = len(data)
        while offset < size and self._language is PrinterLanguage.DEC_PPL and not self._control_representation:
            byte = data[offset]
            offset += 1

            if byte in _BASIC_CONTROLS:
                self._emit_control(byte)
            elif byte == _NEL:
                self._csi.clear()
                self._dec_state = "ground"
                self._emit_control(byte)
            elif self._dec_state == "ground":
                if byte == _ESC:
                    self._dec_state = "escape"
                elif byte == _C1_CSI:
                    self._begin_csi()
                elif byte in _C1_STRINGS:
                    self._begin_string(is_osc=byte == 0x9D)
                else:
                    # Most printer output is ordinary text. Scan it in C rather
                    # than returning to Python for every byte.
                    start = offset - 1
                    next_special = size
                    for marker in _DEC_SPECIAL_BYTES:
                        found = data.find(marker, offset)
                        if found != -1 and found < next_special:
                            next_special = found
                    self._emit_printable(data[start:next_special])
                    offset = next_special
            elif self._dec_state == "escape":
                if byte == ord("["):
                    self._begin_csi()
                elif byte in (ord("P"), ord("X"), ord("]"), ord("^"), ord("_")):
                    self._begin_string(is_osc=byte == ord("]"))
                elif byte == ord("%"):
                    self._dec_state = "percent"
                elif byte == ord("E"):
                    self._emit_control(_NEL)
                    self._dec_state = "ground"
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

    def _emit_printable(self, data: bytes) -> None:
        if self._on_printable is None:
            return
        printable = data.translate(None, _NON_PRINTABLE_BYTES)
        if printable:
            self._on_printable(printable)

    def _emit_control(self, byte: int) -> None:
        if self._on_control is not None:
            self._on_control(byte)

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
        if final in (ord("h"), ord("l")):
            private = body.startswith(b"?")
            parameters = self._numeric_parameters(body[1:] if private else body)
            if parameters is None:
                return
            enabled = final == ord("h")
            for parameter in parameters:
                if not private and parameter == 3:
                    self._control_representation = enabled
                elif not private and parameter == 20:
                    self._line_feed_new_line = enabled
                elif private and parameter == 7:
                    self._autowrap = enabled
                elif private and parameter == 27:
                    self._proportional_spacing = enabled
                elif private and parameter == 29:
                    self._pitch_from_font = enabled
                elif private and parameter == 40:
                    self._carriage_return_new_line = enabled
                elif private and parameter == 41:
                    self._direction = PrintDirection.UNIDIRECTIONAL if enabled else PrintDirection.BIDIRECTIONAL
                elif private and parameter == 58 and enabled and self._supports_proprinter_switching:
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
        self._proportional_spacing = False
        self._pitch_from_font = False
        self._carriage_return_new_line = False
        self._autowrap = True
        self._control_representation = False
        self._line_feed_new_line = False

    def _feed_crm(self, data: bytes, offset: int) -> int:
        patterns = (b"\x1b[3l", b"\x9b3l")
        size = len(data)
        while offset < size and self._control_representation:
            if not self._crm_pending:
                escape = data.find(b"\x1b", offset)
                csi = data.find(b"\x9b", offset)
                starts = tuple(index for index in (escape, csi) if index != -1)
                if not starts:
                    self._emit_crm_bytes(data[offset:])
                    return size
                start = min(starts)
                self._emit_crm_bytes(data[offset:start])
                offset = start

            self._crm_pending.append(data[offset])
            offset += 1
            pending = bytes(self._crm_pending)
            candidates = tuple(pattern for pattern in patterns if pattern.startswith(pending))
            if not candidates:
                trailing_start = pending[-1] if pending[-1] in (_ESC, _C1_CSI) else None
                self._crm_pending.clear()
                self._emit_crm_bytes(pending[:-1] if trailing_start is not None else pending)
                if trailing_start is not None:
                    self._crm_pending.append(trailing_start)
                continue
            if pending in candidates:
                self._crm_pending.clear()
                if self._on_crm_token is not None:
                    self._on_crm_token(pending, "<CSI>3l")
                self._control_representation = False
        return offset

    def _emit_crm_bytes(self, data: bytes) -> None:
        start = 0
        for offset, byte in enumerate(data):
            if 0x20 <= byte <= 0x7E or byte >= 0xA0:
                continue
            self._emit_printable(data[start:offset])
            if self._on_crm_token is not None:
                self._on_crm_token(bytes((byte,)), self._crm_token(byte))
            if byte in (_LF, _FF):
                self._emit_control(byte)
            start = offset + 1
        self._emit_printable(data[start:])

    @staticmethod
    def _crm_token(byte: int) -> str:
        if byte < 0x20:
            name = _C0_NAMES[byte]
        elif byte == 0x7F:
            name = "DEL"
        else:
            name = _C1_NAMES[byte - 0x80]
        return f"<{name or f'X{byte:02X}'}>"

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
