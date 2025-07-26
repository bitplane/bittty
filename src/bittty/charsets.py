"""Character set mappings for terminal emulation."""

# DEC Special Graphics (ESC ( 0)
# Box drawing and special symbols
DEC_SPECIAL_GRAPHICS = {
    "j": "┘",  # Lower right corner
    "k": "┐",  # Upper right corner
    "l": "┌",  # Upper left corner
    "m": "└",  # Lower left corner
    "n": "┼",  # Crossing lines
    "q": "─",  # Horizontal line
    "t": "├",  # Left T
    "u": "┤",  # Right T
    "v": "┴",  # Bottom T
    "w": "┬",  # Top T
    "x": "│",  # Vertical line
    "a": "▒",  # Checkerboard
    "`": "◆",  # Diamond
    "f": "°",  # Degree symbol
    "g": "±",  # Plus/minus
    "~": "·",  # Bullet
    "o": "⎺",  # Scan line 1
    "p": "⎻",  # Scan line 3
    "r": "⎼",  # Scan line 5
    "s": "⎽",  # Scan line 7
    "0": "█",  # Solid block (was ▮)
    "_": " ",  # Non-breaking space
    "{": "π",  # Pi
    "}": "£",  # Pound sterling
    "|": "≠",  # Not equal
    "h": "█",  # NL indicator
    "i": "█",  # VT indicator
    "e": "█",  # LF indicator
    "d": "█",  # CR indicator
    "c": "█",  # FF indicator
    "b": "█",  # HT indicator
    "y": "≤",  # Less than or equal
    "z": "≥",  # Greater than or equal
}

# DEC Supplemental Graphics (ESC ( %5)
# Extended Latin characters
DEC_SUPPLEMENTAL = {
    "\xa0": " ",  # Non-breaking space
    "\xa1": "¡",  # Inverted exclamation
    "\xa2": "¢",  # Cent sign
    "\xa3": "£",  # Pound sign
    "\xa4": "¤",  # Currency sign
    "\xa5": "¥",  # Yen sign
    "\xa6": "¦",  # Broken bar
    "\xa7": "§",  # Section sign
    "\xa8": "¨",  # Diaeresis
    "\xa9": "©",  # Copyright
    "\xaa": "ª",  # Feminine ordinal
    "\xab": "«",  # Left guillemet
    "\xac": "¬",  # Not sign
    "\xad": "\u00ad",  # Soft hyphen
    "\xae": "®",  # Registered trademark
    "\xaf": "¯",  # Macron
    "\xb0": "°",  # Degree sign
    "\xb1": "±",  # Plus-minus
    "\xb2": "²",  # Superscript 2
    "\xb3": "³",  # Superscript 3
    "\xb4": "´",  # Acute accent
    "\xb5": "µ",  # Micro sign
    "\xb6": "¶",  # Pilcrow
    "\xb7": "·",  # Middle dot
    "\xb8": "¸",  # Cedilla
    "\xb9": "¹",  # Superscript 1
    "\xba": "º",  # Masculine ordinal
    "\xbb": "»",  # Right guillemet
    "\xbc": "¼",  # One quarter
    "\xbd": "½",  # One half
    "\xbe": "¾",  # Three quarters
    "\xbf": "¿",  # Inverted question mark
    # ... continues with accented characters À-ÿ
}

# UK National Replacement Character Set (ESC ( A)
# Only differs from ASCII in one position
UK_NATIONAL = {
    "#": "£",  # Pound sign replaces hash
}

# DEC Technical Character Set (ESC ( >)
# Mathematical and technical symbols
DEC_TECHNICAL = {
    # Note: This is a complex set with many symbols
    # Implementation would require a full mapping table
}

# Character set designators
CHARSETS = {
    "A": UK_NATIONAL,  # UK
    "B": {},  # US ASCII (no changes)
    "0": DEC_SPECIAL_GRAPHICS,  # DEC Special Graphics
    "1": {},  # Alternate ROM (same as ASCII usually)
    "2": {},  # Alternate ROM Special Graphics
    "<": DEC_SUPPLEMENTAL,  # DEC Supplemental
    ">": DEC_TECHNICAL,  # DEC Technical
    "H": {},  # Swedish
    "7": {},  # Swedish
    "K": {},  # German
    # Add more as needed
}


def get_charset(designator: str) -> dict:
    """Get character set mapping for a designator."""
    return CHARSETS.get(designator, {})
