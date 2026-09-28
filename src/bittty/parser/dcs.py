"""DCS (Device Control String) operation parser."""

from __future__ import annotations

import re

from ..operations import Operation

# DECCIR: row;column;page;Srend;Satt;Sflag;Pgl;Pgr;Scss;Sdesig
_DECCIR = re.compile(r"([0-9]+);([0-9]+);([0-9]+);([@-O]);([@-O]);([@-O]);([0-3]);([0-3]);([@-O]);((?:[ -/]*[0-~])*)")


def parse_dcs_operation(string_buffer: str, raw: str = "") -> Operation:
    """Return an operation for a DCS sequence."""
    if not string_buffer:
        return Operation("DCS_EMPTY", raw=raw)
    if string_buffer.startswith("$q"):  # DECRQSS - Request Selection or Setting
        return Operation("DECRQSS", (string_buffer[2:],), raw)
    if string_buffer.startswith("+q"):  # XTGETTCAP - Request termcap/terminfo strings
        return Operation("XTGETTCAP", (string_buffer[2:],), raw)
    if string_buffer.startswith("1$t"):  # DECRSPS - restore a DECCIR cursor information report
        match = _DECCIR.fullmatch(string_buffer[3:])
        if match is None:
            return Operation("DCS_UNHANDLED", (string_buffer,), raw)
        row, column, _page, srend, satt, sflag, gl, gr, _scss, designators = match.groups()
        flags = (ord(srend) - 0x40, ord(satt) - 0x40, ord(sflag) - 0x40)
        sets = tuple(re.findall(r"[ -/]*[0-~]", designators))
        return Operation("DECRSPS_CIR", (int(row), int(column), *flags, int(gl), int(gr), sets), raw)
    if string_buffer.startswith("2$t"):  # DECRSPS - restore a DECTABSR tab stop report
        stops = re.match(r"[0-9]+(?:/[0-9]+)*", string_buffer[3:])
        return Operation("DECRSPS_TABS", (tuple(map(int, stops[0].split("/"))) if stops else (),), raw)
    match = re.fullmatch(r"([0-9]*)(?:;([0-9]*))?\|(.*)", string_buffer, re.DOTALL)
    if match is not None:
        clear, lock, body = match.groups()
        try:
            clear, lock = int(clear or 0), int(lock or 0)
        except ValueError:
            return Operation("DCS_UNHANDLED", (string_buffer,), raw)
        if clear in (0, 1) and lock in (0, 1):
            return Operation("DECUDK", (clear, lock, _parse_decudk(body)), raw)
    return Operation("DCS_UNHANDLED", (string_buffer,), raw)


def _parse_decudk(body: str) -> tuple[tuple[int, bytes], ...]:
    """Parse DECUDK key definitions into (key-code, decoded-string) pairs."""
    result = []
    for pair in body.split(";"):
        key, sep, hexstr = pair.partition("/")
        if not sep or not key.isascii() or not key.isdecimal() or not re.fullmatch(r"(?:[0-9a-fA-F]{2})*", hexstr):
            continue
        try:
            result.append((int(key), bytes.fromhex(hexstr)))
        except ValueError:
            continue
    return tuple(result)
