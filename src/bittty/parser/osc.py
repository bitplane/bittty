"""OSC (Operating System Command) operation parser."""

from __future__ import annotations

import logging

from ..operations import Operation


logger = logging.getLogger(__name__)


def parse_osc_operation(string_buffer: str, raw: str = "") -> Operation | None:
    """Return a semantic operation for an OSC sequence."""
    if not string_buffer:
        return Operation("osc", "OSC_EMPTY", raw=raw)

    parsed = _parse_osc(string_buffer)
    if parsed is None:
        return Operation("osc", "OSC_INVALID", (string_buffer,), raw)

    cmd, data = parsed
    if cmd == 0:
        return Operation("title", "SET_ICON_AND_WINDOW_TITLE", (data,), raw)
    if cmd == 1:
        return Operation("title", "SET_ICON_TITLE", (data,), raw)
    if cmd == 2:
        return Operation("title", "SET_WINDOW_TITLE", (data,), raw)
    if cmd == 10 and data == "?":
        return Operation("query", "OSC_FOREGROUND_COLOR", raw=raw)
    if cmd == 11 and data == "?":
        return Operation("query", "OSC_BACKGROUND_COLOR", raw=raw)

    return Operation("osc", "OSC_UNHANDLED", (cmd, data), raw)


def _parse_osc(string_buffer: str) -> tuple[int, str] | None:
    if len(string_buffer) > 2 and string_buffer[1] == ";" and string_buffer[0].isdigit():
        return int(string_buffer[0]), string_buffer[2:]
    if len(string_buffer) > 3 and string_buffer[2] == ";" and string_buffer[:2].isdigit():
        return int(string_buffer[:2]), string_buffer[3:]

    parts = string_buffer.split(";", 1)
    if not parts:
        return None
    try:
        cmd = int(parts[0])
    except ValueError:
        logger.debug(f"Invalid OSC command number: {parts[0] if parts else 'empty'}")
        return None
    return cmd, parts[1] if len(parts) >= 2 else ""
