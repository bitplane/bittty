"""Control Representation Mode decoder."""

from __future__ import annotations

from ._bytes import (
    _C0_NAMES,
    _C1_CSI,
    _C1_NAMES,
    _ESC,
    _FF,
    _LF,
)
from .control import LanguageControl
from .mechanism import PrinterMechanism


class CrmDecoder:
    """Control Representation Mode: controls print as glyphs instead of acting."""

    def __init__(self, mechanism: PrinterMechanism, control: LanguageControl) -> None:
        self._mechanism = mechanism
        self._control = control
        self._crm_pending = bytearray()

    def reset(self) -> None:
        self._crm_pending.clear()

    def feed(self, data: bytes, offset: int) -> int:
        patterns = (b"\x1b[3l", b"\x9b3l")
        size = len(data)
        while offset < size and self._mechanism.control_representation:
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
                self._mechanism.crm_token(pending, "<CSI>3l")
                self._mechanism.control_representation = False
        return offset

    def _emit_crm_bytes(self, data: bytes) -> None:
        start = 0
        for offset, byte in enumerate(data):
            if 0x20 <= byte <= 0x7E or byte >= 0xA0:
                continue
            self._mechanism.print(data[start:offset])
            self._mechanism.crm_token(bytes((byte,)), self._crm_token(byte))
            if byte in (_LF, _FF):
                self._mechanism.control(byte)
            start = offset + 1
        self._mechanism.print(data[start:])

    @staticmethod
    def _crm_token(byte: int) -> str:
        if byte < 0x20:
            name = _C0_NAMES[byte]
        elif byte == 0x7F:
            name = "DEL"
        else:
            name = _C1_NAMES[byte - 0x80]
        return f"<{name or f'X{byte:02X}'}>"
