"""Simple escape sequence operation parser."""

from __future__ import annotations

from ..operations import Operation


ESCAPE_OPERATION_NAMES = {
    "c": ("screen", "RIS", ()),
    "D": ("control", "IND", ()),
    "M": ("control", "RI", ()),
    "7": ("cursor", "SAVE", ()),
    "8": ("cursor", "RESTORE", ()),
    "=": ("mode", "DECKPAM", ()),
    ">": ("mode", "DECKPNM", ()),
    "\\": ("control", "ST", ()),
    "N": ("escape", "SS2", ()),
    "O": ("escape", "SS3", ()),
    "E": ("control", "NEL", ()),
    "H": ("control", "HTS", ()),
}


def parse_escape_operation(data: str) -> Operation | None:
    """Return a semantic operation for a simple ESC sequence."""
    if len(data) < 2:
        return None

    parts = ESCAPE_OPERATION_NAMES.get(data[1])
    if parts is None:
        return None

    kind, name, args = parts
    return Operation(kind, name, args, data)


CHARSET_OPERATION_NAMES = {
    "(": "SCS_G0",
    ")": "SCS_G1",
    "*": "SCS_G2",
    "+": "SCS_G3",
}


def parse_charset_operation(data: str) -> Operation | None:
    """Return a semantic operation for a charset designation sequence."""
    if len(data) < 3:
        return None

    name = CHARSET_OPERATION_NAMES.get(data[1])
    if name is None:
        return None

    return Operation("charset", name, (data[2],), data)
