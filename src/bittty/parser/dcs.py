"""DCS (Device Control String) operation parser."""

from __future__ import annotations

from ..operations import Operation


def parse_dcs_operation(string_buffer: str, raw: str = "") -> Operation:
    """Return an operation for a DCS sequence."""
    if not string_buffer:
        return Operation("DCS_EMPTY", raw=raw)
    if string_buffer.startswith("$q"):  # DECRQSS - Request Selection or Setting
        return Operation("DECRQSS", (string_buffer[2:],), raw)
    if string_buffer.startswith("+q"):  # XTGETTCAP - Request termcap/terminfo strings
        return Operation("XTGETTCAP", (string_buffer[2:],), raw)
    if "|" in string_buffer:  # DECUDK - User-Defined Keys (Pc;Pl | Ky1/St1;Ky2/St2 ...)
        return Operation("DECUDK", (_parse_decudk(string_buffer),), raw)
    return Operation("DCS_UNHANDLED", (string_buffer,), raw)


def _parse_decudk(string_buffer: str) -> tuple[tuple[int, str], ...]:
    """Parse DECUDK key definitions into (key-code, decoded-string) pairs."""
    _, _, body = string_buffer.partition("|")
    result = []
    for pair in body.split(";"):
        key, sep, hexstr = pair.partition("/")
        if not sep:
            continue
        try:
            result.append((int(key), bytes.fromhex(hexstr).decode("latin-1")))
        except ValueError:
            continue
    return tuple(result)
