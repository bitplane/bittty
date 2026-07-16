"""OSC (Operating System Command) operation parser."""

from __future__ import annotations

import logging

from ..operations import Operation


logger = logging.getLogger(__name__)


def parse_osc_operation(string_buffer: str, raw: str = "") -> Operation | None:
    """Return a semantic operation for an OSC sequence."""
    if not string_buffer:
        return Operation("OSC_EMPTY", raw=raw)

    parsed = _parse_osc(string_buffer)
    if parsed is None:
        return Operation("OSC_INVALID", (string_buffer,), raw)

    cmd, data = parsed
    if cmd == 0:
        return Operation("SET_ICON_AND_WINDOW_TITLE", (data,), raw)
    if cmd == 1:
        return Operation("SET_ICON_TITLE", (data,), raw)
    if cmd == 2:
        return Operation("SET_WINDOW_TITLE", (data,), raw)
    if cmd == 7:  # Report working directory (file:// URI)
        return Operation("OSC_CWD", (data,), raw)
    if cmd == 8:  # Hyperlink: OSC 8 ; params ; URI  (empty URI closes)
        _, _, uri = data.partition(";")
        return Operation("OSC_HYPERLINK", (uri,), raw)
    if cmd == 9:  # Desktop notification (iTerm)
        return Operation("OSC_NOTIFY", (data,), raw)
    if cmd == 133:  # Shell integration prompt/command marks (FinalTerm/iTerm)
        return Operation("OSC_SHELL_MARK", (data,), raw)
    if cmd == 777:  # rxvt: OSC 777 ; notify ; title ; body
        parts = data.split(";")
        message = "; ".join(parts[1:]) if len(parts) >= 3 and parts[0] == "notify" else data
        return Operation("OSC_NOTIFY", (message,), raw)
    if cmd == 52:  # Clipboard: OSC 52 ; selection ; base64-data | ?
        selection, _, payload = data.partition(";")
        return Operation("OSC_CLIPBOARD", (selection, payload), raw)
    if cmd == 4:
        return Operation("OSC_SET_PALETTE", (data,), raw)
    if cmd == 10:
        return Operation("OSC_FOREGROUND", (data,), raw)
    if cmd == 11:
        return Operation("OSC_BACKGROUND", (data,), raw)
    if cmd == 12:
        return Operation("OSC_CURSOR", (data,), raw)
    if cmd == 104:
        return Operation("OSC_RESET_PALETTE", (data,), raw)
    if cmd == 110:
        return Operation("OSC_RESET_FOREGROUND", (), raw)
    if cmd == 111:
        return Operation("OSC_RESET_BACKGROUND", (), raw)
    if cmd == 112:
        return Operation("OSC_RESET_CURSOR", (), raw)

    return Operation("OSC_UNHANDLED", (cmd, data), raw)


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
