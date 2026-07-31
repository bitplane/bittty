"""Control-byte constants and names shared by the printer language decoders."""

from __future__ import annotations

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
_HTS = 0x88
_VTS = 0x8A
_SS2 = 0x8E
_SS3 = 0x8F
_SO = 0x0E
_SI = 0x0F
_BASIC_CONTROLS = frozenset((_BS, _HT, _LF, _VT, _FF, _CR))
_DEC_SPECIAL_BYTES = (
    b"\x08",
    b"\x09",
    b"\x0a",
    b"\x0b",
    b"\x0c",
    b"\x0d",
    b"\x0e",
    b"\x0f",
    b"\x1b",
    b"\x85",
    b"\x88",
    b"\x8a",
    b"\x8e",
    b"\x8f",
    b"\x90",
    b"\x98",
    b"\x9b",
    b"\x9d",
    b"\x9e",
    b"\x9f",
)
_NON_PRINTABLE_BYTES = bytes(range(0x20)) + b"\x7f" + bytes(range(0x80, 0xA0))
_MAX_CSI = 128
_IBM_BRACKET_LENGTH_COMMANDS = b"@AFKTZ\\ghim"
_IBM_SPECIAL_BYTES = tuple(
    bytes((byte,))
    for byte in (0x00, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x12, 0x13, 0x14, 0x18, 0x1B)
)
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
