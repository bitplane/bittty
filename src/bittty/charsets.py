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

# DEC Supplemental Graphic (ESC ( %5): the upper half of the DEC multinational set, so GL
# code c shows c + 0x80, save DEC's own glyphs and the reserved positions (a reversed "?",
# as xterm's charsets.h renders them).
_RESERVED = "\u2426"
DEC_SUPPLEMENTAL = {chr(code): chr(code + 0x80) for code in range(0x21, 0x7F)} | {
    "(": "¤",
    "W": "Œ",
    "]": "Ÿ",
    "w": "œ",
    "}": "ÿ",
    **dict.fromkeys("$&,-./48>P^p~", _RESERVED),
}

# UK National Replacement Character Set (ESC ( A)
# Only differs from ASCII in one position
UK_NATIONAL = {
    "#": "£",  # Pound sign replaces hash
}

# Danish/Norwegian National Character Set (ESC ( E)
DANISH_NORWEGIAN = {
    "[": "Æ",
    "\\": "Ø",
    "]": "Å",
    "`": "æ",
    "{": "ø",
    "|": "å",
}

# Danish/Norwegian Alternative Character Set (ESC ( 6)
DANISH_NORWEGIAN_ALT = {
    "@": "Ä",
    "[": "Æ",
    "\\": "Ø",
    "]": "Å",
    "^": "Ü",
    "`": "ä",
    "{": "æ",
    "|": "ø",
    "}": "å",
    "~": "ü",
}

# Dutch National Character Set (ESC ( 4)
DUTCH_NATIONAL = {
    "#": "£",
    "@": "¾",
    "[": "ĳ",
    "\\": "½",
    "]": "¦",
    "`": "`",
    "{": "¨",
    "|": "ƒ",
    "}": "¼",
    "~": "´",
}

# Finnish National Character Set (ESC ( C or ESC ( 5)
FINNISH_NATIONAL = {
    "[": "Ä",
    "\\": "Ö",
    "]": "Å",
    "^": "Ü",
    "`": "é",
    "{": "ä",
    "|": "ö",
    "}": "å",
    "~": "ü",
}

# French National Character Set (ESC ( R)
FRENCH_NATIONAL = {
    "#": "£",
    "@": "à",
    "[": "°",
    "\\": "ç",
    "]": "§",
    "`": "`",
    "{": "é",
    "|": "ù",
    "}": "è",
    "~": "¨",
}

# French Canadian National Character Set (ESC ( Q)
FRENCH_CANADIAN = {
    "@": "à",
    "[": "â",
    "\\": "ç",
    "]": "ê",
    "^": "î",
    "`": "ô",
    "{": "é",
    "|": "ù",
    "}": "è",
    "~": "û",
}

# German National Character Set (ESC ( K)
GERMAN_NATIONAL = {
    "@": "§",
    "[": "Ä",
    "\\": "Ö",
    "]": "Ü",
    "`": "ä",
    "{": "ö",
    "|": "ü",
    "}": "ß",
}

# Italian National Character Set (ESC ( Y)
ITALIAN_NATIONAL = {
    "#": "£",
    "@": "§",
    "[": "°",
    "\\": "ç",
    "]": "é",
    "`": "ù",
    "{": "à",
    "|": "ò",
    "}": "è",
    "~": "ì",
}

# Japanese Roman Character Set (ESC ( J)
JAPANESE_ROMAN = {
    "\\": "¥",
    "~": "¯",
}

# Portuguese National Character Set (ESC ( % 6)
PORTUGUESE_NATIONAL = {
    "[": "Ã",
    "\\": "Ç",
    "]": "Õ",
    "`": "ã",
    "{": "ç",
    "|": "õ",
}

# Spanish National Character Set (ESC ( Z)
SPANISH_NATIONAL = {
    "#": "£",
    "@": "§",
    "[": "¡",
    "\\": "Ñ",
    "]": "¿",
    "`": "˚",
    "{": "ñ",
    "|": "ç",
}

# Swedish National Character Set (ESC ( H or ESC ( 7)
SWEDISH_NATIONAL = {
    "@": "É",
    "[": "Ä",
    "\\": "Ö",
    "]": "Å",
    "^": "Ü",
    "`": "é",
    "{": "ä",
    "|": "ö",
    "}": "å",
    "~": "ü",
}

# Swiss National Character Set (ESC ( =)
SWISS_NATIONAL = {
    "#": "ù",
    "@": "à",
    "[": "é",
    "\\": "ç",
    "]": "ê",
    "^": "î",
    "_": "è",
    "`": "ô",
    "{": "ä",
    "|": "ö",
    "}": "ü",
    "~": "û",
}

# DEC Technical Character Set (ESC ( >)
# Mathematical and technical symbols for VT330+
DEC_TECHNICAL = {
    # Row 2 (0x21-0x2F) - Mathematical operators and brackets
    "!": "√",  # Radical symbol bottom
    '"': "┌",  # Box drawings light down and right (corrected)
    "#": "─",  # Box drawings light horizontal
    "$": "⌠",  # Top half integral
    "%": "⌡",  # Bottom half integral
    "&": "│",  # Box drawings light vertical
    "'": "⌈",  # Left square bracket upper corner
    "(": "⌊",  # Left square bracket lower corner
    ")": "⌉",  # Right square bracket upper corner
    "*": "⌋",  # Right square bracket lower corner
    "+": "⎛",  # Left parenthesis upper hook
    ",": "⎝",  # Left parenthesis lower hook
    "-": "⎞",  # Right parenthesis upper hook
    ".": "⎠",  # Right parenthesis lower hook
    "/": "⎨",  # Left curly bracket middle piece
    # Row 3 (0x30-0x3F) - More brackets and operators
    "0": "⎬",  # Right curly bracket middle piece
    "1": "⎲",  # Summation top
    "2": "⎳",  # Summation bottom
    "3": "╲",  # Box drawings light diagonal upper right to lower left
    "4": "╱",  # Box drawings light diagonal upper left to lower right
    "5": "┐",  # Box drawings light down and left
    "6": "┘",  # Box drawings light up and left
    "7": "❭",  # Heavy right-pointing angle bracket ornament
    # "8", "9", ":", ";" are undefined
    "<": "≤",  # Less-than or equal to
    "=": "≠",  # Not equal to
    ">": "≥",  # Greater-than or equal to
    "?": "∫",  # Integral
    # Row 4 (0x40-0x4F) - Mathematical symbols and Greek capitals
    "@": "∴",  # Therefore
    "A": "∝",  # Proportional to
    "B": "∞",  # Infinity
    "C": "÷",  # Division sign
    "D": "Δ",  # Greek capital letter delta
    "E": "∇",  # Nabla
    "F": "Φ",  # Greek capital letter phi
    "G": "Γ",  # Greek capital letter gamma
    "H": "∼",  # Tilde operator
    "I": "≃",  # Asymptotically equal to
    "J": "Θ",  # Greek capital letter theta
    "K": "×",  # Multiplication sign
    "L": "Λ",  # Greek capital letter lambda
    "M": "⇔",  # Left right double arrow
    "N": "⇒",  # Rightwards double arrow
    "O": "≡",  # Identical to
    # Row 5 (0x50-0x5F) - More Greek capitals and set theory
    "P": "Π",  # Greek capital letter pi
    "Q": "Ψ",  # Greek capital letter psi
    # "R" is undefined
    "S": "Σ",  # Greek capital letter sigma
    # "T", "U" are undefined
    "V": "√",  # Square root
    "W": "Ω",  # Greek capital letter omega
    "X": "Ξ",  # Greek capital letter xi
    "Y": "Υ",  # Greek capital letter upsilon
    "Z": "⊂",  # Subset of
    "[": "⊃",  # Superset of
    "\\": "∩",  # Intersection
    "]": "∪",  # Union
    "^": "∧",  # Logical and
    "_": "∨",  # Logical or
    # Row 6 (0x60-0x6F) - Greek lowercase letters
    "`": "¬",  # Not sign
    "a": "α",  # Greek small letter alpha
    "b": "β",  # Greek small letter beta
    "c": "χ",  # Greek small letter chi
    "d": "δ",  # Greek small letter delta
    "e": "ε",  # Greek small letter epsilon
    "f": "φ",  # Greek small letter phi
    "g": "γ",  # Greek small letter gamma
    "h": "η",  # Greek small letter eta
    "i": "ι",  # Greek small letter iota
    "j": "θ",  # Greek small letter theta
    "k": "κ",  # Greek small letter kappa
    "l": "λ",  # Greek small letter lambda
    # "m" is undefined
    "n": "ν",  # Greek small letter nu
    "o": "∂",  # Partial differential
    # Row 7 (0x70-0x7E) - More Greek lowercase and arrows
    "p": "π",  # Greek small letter pi
    "q": "ψ",  # Greek small letter psi
    "r": "ρ",  # Greek small letter rho
    "s": "σ",  # Greek small letter sigma
    "t": "τ",  # Greek small letter tau
    # "u" is undefined
    "v": "ƒ",  # Latin small letter f with hook (function)
    "w": "ω",  # Greek small letter omega
    "x": "ξ",  # Greek small letter xi
    "y": "υ",  # Greek small letter upsilon
    "z": "ζ",  # Greek small letter zeta
    "{": "←",  # Leftwards arrow
    "|": "↑",  # Upwards arrow
    "}": "→",  # Rightwards arrow
    "~": "↓",  # Downwards arrow
}

# Character set designators
# The VT52 graphics set, as xterm 407 renders it (ESC F in VT52 mode); the 3/, 5/ and 7/
# fractions and the reserved codes have no character and show as blanks.
VT52_GRAPHICS = dict(zip("_`abcdefghijklmnopqrstuvwxyz{|}~", "  ▮⅟   °±→…÷↓⎺⎺⎻⎻⎼⎼⎽⎽₀₁₂₃₄₅₆₇₈₉¶"))

CHARSETS = {
    "A": UK_NATIONAL,  # UK
    "B": {},  # US ASCII (no changes)
    "0": DEC_SPECIAL_GRAPHICS,  # DEC Special Graphics
    "1": {},  # Alternate ROM (same as ASCII usually)
    "2": {},  # Alternate ROM Special Graphics
    "U": {},  # Linux console: IBM PC ROM / CP437 (passthrough under Unicode)
    "%5": DEC_SUPPLEMENTAL,  # DEC Supplemental Graphic ("<", the user-preferred set, resolves to a set)
    ">": DEC_TECHNICAL,  # DEC Technical
    "4": DUTCH_NATIONAL,  # Dutch
    "5": FINNISH_NATIONAL,  # Finnish (alternative)
    "6": DANISH_NORWEGIAN_ALT,  # Danish/Norwegian alternative
    "7": SWEDISH_NATIONAL,  # Swedish (alternative)
    "=": SWISS_NATIONAL,  # Swiss
    "C": FINNISH_NATIONAL,  # Finnish
    "E": DANISH_NORWEGIAN,  # Danish/Norwegian
    "H": SWEDISH_NATIONAL,  # Swedish
    "J": JAPANESE_ROMAN,  # Japanese Roman
    "K": GERMAN_NATIONAL,  # German
    "Q": FRENCH_CANADIAN,  # French Canadian
    "R": FRENCH_NATIONAL,  # French
    "Y": ITALIAN_NATIONAL,  # Italian
    "Z": SPANISH_NATIONAL,  # Spanish
    "%6": PORTUGUESE_NATIONAL,  # Portuguese (multi-char designator)
    "vt52": VT52_GRAPHICS,  # no designator: VT52 mode selects it with ESC F
}

# SCS designators whose recognition is controlled by DECNRCM on terminals
# which implement that mode. Older profiles such as the VT100 have no
# DECNRCM switch and retain their model-specific SCS behaviour.
NATIONAL_CHARSET_DESIGNATORS = frozenset(
    {"A", "4", "5", "6", "7", "=", "C", "E", "H", "J", "K", "Q", "R", "Y", "Z", "%6"}
)


# Sets DECAUPSS can make the user-preferred supplemental set, by (DECAUPSS Pn, designator):
# Pn 0 names a 94-character set.
SUPPLEMENTAL_SETS = frozenset({(0, "%5")})


def get_charset(designator: str) -> dict:
    """Get character set mapping for a designator."""
    return CHARSETS.get(designator, {})
