"""Simple escape sequence operation parser."""

from __future__ import annotations

from ..operations import Operation


ESCAPE_OPERATION_NAMES = {
    "c": ("RIS", ()),
    "D": ("IND", ()),
    "M": ("RI", ()),
    "7": ("SAVE", ()),
    "8": ("RESTORE", ()),
    "=": ("DECKPAM", ()),
    ">": ("DECKPNM", ()),
    "\\": ("ST", ()),
    "N": ("SS2", ()),
    "O": ("SS3", ()),
    "E": ("NEL", ()),
    "H": ("HTS", ()),
    "Z": ("DA1", ()),  # DECID — obsolete "identify", answered like primary DA
    # Locking shifts (ISO 2022): invoke a G-set into GL (n/o) or GR (~/}/|) persistently.
    "n": ("LS2", ()),  # G2 -> GL
    "o": ("LS3", ()),  # G3 -> GL
    "~": ("LS1R", ()),  # G1 -> GR
    "}": ("LS2R", ()),  # G2 -> GR
    "|": ("LS3R", ()),  # G3 -> GR
}


def parse_escape_operation(data: str) -> Operation | None:
    """Return a semantic operation for a simple ESC sequence."""
    if len(data) < 2:
        return None

    parts = ESCAPE_OPERATION_NAMES.get(data[1])
    if parts is None:
        return None

    name, args = parts
    return Operation(name, args, data)


def parse_hash_operation(data: str) -> Operation | None:
    """Return a semantic operation for an ESC # n sequence (DECALN is ESC # 8)."""
    if len(data) < 3:
        return None
    if data[2] == "8":
        return Operation("DECALN", (), data)
    return None


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

    return Operation(name, (data[2],), data)
