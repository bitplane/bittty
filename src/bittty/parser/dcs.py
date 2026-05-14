"""DCS (Device Control String) operation parser."""

from __future__ import annotations

from ..operations import Operation


def parse_dcs_operation(string_buffer: str, raw: str = "") -> Operation:
    """Return an operation for a DCS sequence."""
    if not string_buffer:
        return Operation("dcs", "DCS_EMPTY", raw=raw)
    return Operation("dcs", "DCS_UNHANDLED", (string_buffer,), raw)
