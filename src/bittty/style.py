"""Style merging for ANSI escape sequences."""

from __future__ import annotations

from functools import lru_cache


# Pattern tuples ordered by popularity (most common first)
RESET_PATTERNS = ("[0m", "[m", ";0;", "[0;", ";0m")

# Colors are most common
FG_BLACK_PATTERNS = (";30;", "[30;", ";30m", "[30m")
FG_RED_PATTERNS = (";31;", "[31;", ";31m", "[31m")
FG_GREEN_PATTERNS = (";32;", "[32;", ";32m", "[32m")
FG_YELLOW_PATTERNS = (";33;", "[33;", ";33m", "[33m")
FG_BLUE_PATTERNS = (";34;", "[34;", ";34m", "[34m")
FG_MAGENTA_PATTERNS = (";35;", "[35;", ";35m", "[35m")
FG_CYAN_PATTERNS = (";36;", "[36;", ";36m", "[36m")
FG_WHITE_PATTERNS = (";37;", "[37;", ";37m", "[37m")
FG_DEFAULT_PATTERNS = (";39;", "[39;", ";39m", "[39m")

BG_BLACK_PATTERNS = (";40;", "[40;", ";40m", "[40m")
BG_RED_PATTERNS = (";41;", "[41;", ";41m", "[41m")
BG_GREEN_PATTERNS = (";42;", "[42;", ";42m", "[42m")
BG_YELLOW_PATTERNS = (";43;", "[43;", ";43m", "[43m")
BG_BLUE_PATTERNS = (";44;", "[44;", ";44m", "[44m")
BG_MAGENTA_PATTERNS = (";45;", "[45;", ";45m", "[45m")
BG_CYAN_PATTERNS = (";46;", "[46;", ";46m", "[46m")
BG_WHITE_PATTERNS = (";47;", "[47;", ";47m", "[47m")
BG_DEFAULT_PATTERNS = (";49;", "[49;", ";49m", "[49m")

# Bright colors
FG_BRIGHT_BLACK_PATTERNS = (";90;", "[90;", ";90m", "[90m")
FG_BRIGHT_RED_PATTERNS = (";91;", "[91;", ";91m", "[91m")
FG_BRIGHT_GREEN_PATTERNS = (";92;", "[92;", ";92m", "[92m")
FG_BRIGHT_YELLOW_PATTERNS = (";93;", "[93;", ";93m", "[93m")
FG_BRIGHT_BLUE_PATTERNS = (";94;", "[94;", ";94m", "[94m")
FG_BRIGHT_MAGENTA_PATTERNS = (";95;", "[95;", ";95m", "[95m")
FG_BRIGHT_CYAN_PATTERNS = (";96;", "[96;", ";96m", "[96m")
FG_BRIGHT_WHITE_PATTERNS = (";97;", "[97;", ";97m", "[97m")

BG_BRIGHT_BLACK_PATTERNS = (";100;", "[100;", ";100m", "[100m")
BG_BRIGHT_RED_PATTERNS = (";101;", "[101;", ";101m", "[101m")
BG_BRIGHT_GREEN_PATTERNS = (";102;", "[102;", ";102m", "[102m")
BG_BRIGHT_YELLOW_PATTERNS = (";103;", "[103;", ";103m", "[103m")
BG_BRIGHT_BLUE_PATTERNS = (";104;", "[104;", ";104m", "[104m")
BG_BRIGHT_MAGENTA_PATTERNS = (";105;", "[105;", ";105m", "[105m")
BG_BRIGHT_CYAN_PATTERNS = (";106;", "[106;", ";106m", "[106m")
BG_BRIGHT_WHITE_PATTERNS = (";107;", "[107;", ";107m", "[107m")

# Text attributes (ordered by popularity)
BOLD_PATTERNS = (";1;", "[1;", ";1m", "[1m")
UNDERLINE_PATTERNS = (";4;", "[4;", ";4m", "[4m")
DIM_PATTERNS = (";2;", "[2;", ";2m", "[2m")
ITALIC_PATTERNS = (";3;", "[3;", ";3m", "[3m")
REVERSE_PATTERNS = (";7;", "[7;", ";7m", "[7m")
BLINK_PATTERNS = (";5;", "[5;", ";5m", "[5m")
STRIKE_PATTERNS = (";9;", "[9;", ";9m", "[9m")
CONCEAL_PATTERNS = (";8;", "[8;", ";8m", "[8m")

# Reset patterns for attributes
NOT_BOLD_PATTERNS = (";22;", "[22;", ";22m", "[22m", ";21;", "[21;", ";21m", "[21m")
NOT_DIM_PATTERNS = (";22;", "[22;", ";22m", "[22m")
NOT_ITALIC_PATTERNS = (";23;", "[23;", ";23m", "[23m")
NOT_UNDERLINE_PATTERNS = (";24;", "[24;", ";24m", "[24m")
NOT_BLINK_PATTERNS = (";25;", "[25;", ";25m", "[25m")
NOT_REVERSE_PATTERNS = (";27;", "[27;", ";27m", "[27m")
NOT_CONCEAL_PATTERNS = (";28;", "[28;", ";28m", "[28m")
NOT_STRIKE_PATTERNS = (";29;", "[29;", ";29m", "[29m")


@lru_cache(maxsize=20000)
def has_pattern(ansi: str, patterns: tuple) -> bool:
    """Check if ANSI sequence contains any of the patterns."""
    for pattern in patterns:
        if pattern in ansi:
            return True
    return False


@lru_cache(maxsize=20000)
def _extract_indexed_color(ansi: str, base_code: str) -> str:
    """Extracts 256-color or true-color parameters from an ANSI sequence."""
    if ";5;" in ansi or ";2;" in ansi:
        # Strip the escape prefix and m suffix
        if ansi.startswith("\033[") or ansi.startswith("\x1b["):
            ansi = ansi[2:]
        parts = ansi.rstrip("m").split(";")
        for i, part in enumerate(parts):
            if part == base_code:
                if len(parts) > i + 1 and parts[i + 1] == "5":
                    if len(parts) > i + 2:
                        return f"{base_code};5;{parts[i+2]}"
                elif len(parts) > i + 4 and parts[i + 1] == "2":
                    return f"{base_code};2;{parts[i+2]};{parts[i+3]};{parts[i+4]}"
    return ""


@lru_cache(maxsize=20000)
def extract_fg_color(ansi: str) -> str:
    """Extract foreground color parameter from ANSI sequence."""
    # Check for 256-color or true-color first
    indexed_color = _extract_indexed_color(ansi, "38")
    if indexed_color:
        return indexed_color

    # Check patterns in order of popularity
    if has_pattern(ansi, FG_RED_PATTERNS):
        return "31"
    elif has_pattern(ansi, FG_GREEN_PATTERNS):
        return "32"
    elif has_pattern(ansi, FG_YELLOW_PATTERNS):
        return "33"
    elif has_pattern(ansi, FG_BLUE_PATTERNS):
        return "34"
    elif has_pattern(ansi, FG_MAGENTA_PATTERNS):
        return "35"
    elif has_pattern(ansi, FG_CYAN_PATTERNS):
        return "36"
    elif has_pattern(ansi, FG_WHITE_PATTERNS):
        return "37"
    elif has_pattern(ansi, FG_BLACK_PATTERNS):
        return "30"
    elif has_pattern(ansi, FG_DEFAULT_PATTERNS):
        return "39"
    elif has_pattern(ansi, FG_BRIGHT_RED_PATTERNS):
        return "91"
    elif has_pattern(ansi, FG_BRIGHT_GREEN_PATTERNS):
        return "92"
    elif has_pattern(ansi, FG_BRIGHT_YELLOW_PATTERNS):
        return "93"
    elif has_pattern(ansi, FG_BRIGHT_BLUE_PATTERNS):
        return "94"
    elif has_pattern(ansi, FG_BRIGHT_MAGENTA_PATTERNS):
        return "95"
    elif has_pattern(ansi, FG_BRIGHT_CYAN_PATTERNS):
        return "96"
    elif has_pattern(ansi, FG_BRIGHT_WHITE_PATTERNS):
        return "97"
    elif has_pattern(ansi, FG_BRIGHT_BLACK_PATTERNS):
        return "90"
    return ""


@lru_cache(maxsize=20000)
def extract_bg_color(ansi: str) -> str:
    """Extract background color parameter from ANSI sequence."""
    # Check for 256-color or true-color first
    indexed_color = _extract_indexed_color(ansi, "48")
    if indexed_color:
        return indexed_color

    # Check patterns in order of popularity
    if has_pattern(ansi, BG_BLACK_PATTERNS):
        return "40"
    elif has_pattern(ansi, BG_RED_PATTERNS):
        return "41"
    elif has_pattern(ansi, BG_GREEN_PATTERNS):
        return "42"
    elif has_pattern(ansi, BG_YELLOW_PATTERNS):
        return "43"
    elif has_pattern(ansi, BG_BLUE_PATTERNS):
        return "44"
    elif has_pattern(ansi, BG_MAGENTA_PATTERNS):
        return "45"
    elif has_pattern(ansi, BG_CYAN_PATTERNS):
        return "46"
    elif has_pattern(ansi, BG_WHITE_PATTERNS):
        return "47"
    elif has_pattern(ansi, BG_DEFAULT_PATTERNS):
        return "49"
    elif has_pattern(ansi, BG_BRIGHT_BLACK_PATTERNS):
        return "100"
    elif has_pattern(ansi, BG_BRIGHT_RED_PATTERNS):
        return "101"
    elif has_pattern(ansi, BG_BRIGHT_GREEN_PATTERNS):
        return "102"
    elif has_pattern(ansi, BG_BRIGHT_YELLOW_PATTERNS):
        return "103"
    elif has_pattern(ansi, BG_BRIGHT_BLUE_PATTERNS):
        return "104"
    elif has_pattern(ansi, BG_BRIGHT_MAGENTA_PATTERNS):
        return "105"
    elif has_pattern(ansi, BG_BRIGHT_CYAN_PATTERNS):
        return "106"
    elif has_pattern(ansi, BG_BRIGHT_WHITE_PATTERNS):
        return "107"
    return ""


@lru_cache(maxsize=20000)
def get_background(ansi: str) -> str:
    """Get just the background color from an ANSI sequence.

    Args:
        ansi: ANSI escape sequence

    Returns:
        ANSI sequence with just the background color, or empty string
    """
    bg_color = extract_bg_color(ansi)
    if bg_color:
        return f"\033[{bg_color}m"
    return ""


@lru_cache(maxsize=20000)
def _parse_ansi_to_tuple(ansi: str) -> tuple:
    """Parse an ANSI escape sequence into a canonical tuple representation."""
    if not ansi:
        return (None, None, None, None, None, None, None, None, None, None)

    if has_pattern(ansi, RESET_PATTERNS):
        return (None, None, None, None, None, None, None, None, None, None)

    fg = extract_fg_color(ansi)
    bg = extract_bg_color(ansi)
    
    bold = None
    if has_pattern(ansi, BOLD_PATTERNS):
        bold = True
    elif has_pattern(ansi, NOT_BOLD_PATTERNS):
        bold = False

    dim = None
    if has_pattern(ansi, DIM_PATTERNS):
        dim = True
    elif has_pattern(ansi, NOT_DIM_PATTERNS):
        dim = False

    italic = None
    if has_pattern(ansi, ITALIC_PATTERNS):
        italic = True
    elif has_pattern(ansi, NOT_ITALIC_PATTERNS):
        italic = False

    underline = None
    if has_pattern(ansi, UNDERLINE_PATTERNS):
        underline = True
    elif has_pattern(ansi, NOT_UNDERLINE_PATTERNS):
        underline = False

    blink = None
    if has_pattern(ansi, BLINK_PATTERNS):
        blink = True
    elif has_pattern(ansi, NOT_BLINK_PATTERNS):
        blink = False

    reverse = None
    if has_pattern(ansi, REVERSE_PATTERNS):
        reverse = True
    elif has_pattern(ansi, NOT_REVERSE_PATTERNS):
        reverse = False

    conceal = None
    if has_pattern(ansi, CONCEAL_PATTERNS):
        conceal = True
    elif has_pattern(ansi, NOT_CONCEAL_PATTERNS):
        conceal = False

    strike = None
    if has_pattern(ansi, STRIKE_PATTERNS):
        strike = True
    elif has_pattern(ansi, NOT_STRIKE_PATTERNS):
        strike = False

    return (fg, bg, bold, dim, italic, underline, blink, reverse, conceal, strike)


@lru_cache(maxsize=20000)
def _tuple_to_ansi(style_tuple: tuple) -> str:
    """Convert a style tuple back to an ANSI escape sequence."""
    fg, bg, bold, dim, italic, underline, blink, reverse, conceal, strike = style_tuple
    
    params = []
    if fg:
        params.append(fg)
    if bg:
        params.append(bg)

    if bold is True:
        params.append("1")
    elif bold is False:
        params.append("22")

    if dim is True:
        params.append("2")
    elif dim is False:
        params.append("22")

    if italic is True:
        params.append("3")
    elif italic is False:
        params.append("23")

    if underline is True:
        params.append("4")
    elif underline is False:
        params.append("24")

    if blink is True:
        params.append("5")
    elif blink is False:
        params.append("25")

    if reverse is True:
        params.append("7")
    elif reverse is False:
        params.append("27")

    if conceal is True:
        params.append("8")
    elif conceal is False:
        params.append("28")

    if strike is True:
        params.append("9")
    elif strike is False:
        params.append("29")

    # Always return an ANSI string, even if empty params, unless it's a full reset
    if not params and style_tuple != (None, None, False, False, False, False, False, False, False, False):
        return ""
    elif not params and style_tuple == (None, None, False, False, False, False, False, False, False, False):
        return "\033[0m" # Explicitly return reset for a full reset tuple

    # Sort parameters for consistent output and better caching
    sorted_params = sorted(list(params))
    return f"\033[{';'.join(sorted_params)}m"


@lru_cache(maxsize=20000)
def merge_ansi_styles(base: str, new: str) -> str:
    """Merge two ANSI style sequences."""
    if not base:
        return new
    if not new:
        return base
    if has_pattern(new, RESET_PATTERNS):
        return new

    base_tuple = _parse_ansi_to_tuple(base)
    new_tuple = _parse_ansi_to_tuple(new)

    # Unpack tuples for merging
    base_fg, base_bg, base_bold, base_dim, base_italic, base_underline, base_blink, base_reverse, base_conceal, base_strike = base_tuple
    new_fg, new_bg, new_bold, new_dim, new_italic, new_underline, new_blink, new_reverse, new_conceal, new_strike = new_tuple

    # Merge fields - new takes precedence. If new is None, use base.
    final_fg = new_fg if new_fg is not None else base_fg
    final_bg = new_bg if new_bg is not None else base_bg
    final_bold = new_bold if new_bold is not None else base_bold
    final_dim = new_dim if new_dim is not None else base_dim
    final_italic = new_italic if new_italic is not None else base_italic
    final_underline = new_underline if new_underline is not None else base_underline
    final_blink = new_blink if new_blink is not None else base_blink
    final_reverse = new_reverse if new_reverse is not None else base_reverse
    final_conceal = new_conceal if new_conceal is not None else base_conceal
    final_strike = new_strike if new_strike is not None else base_strike

    merged_tuple = (
        final_fg, final_bg, final_bold, final_dim, final_italic, 
        final_underline, final_blink, final_reverse, final_conceal, final_strike
    )

    return _tuple_to_ansi(merged_tuple)




