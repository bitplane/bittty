"""
ANSI Sequence Cache: LRU-cached functions for generating ANSI escape sequences.

This module provides high-performance ANSI sequence generation by caching
commonly used combinations of colors and styles.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Tuple


@lru_cache(maxsize=1024)
def get_color_code(fg: Optional[int] = None, bg: Optional[int] = None) -> str:
    """
    Generate ANSI color code for 256-color palette.

    Args:
        fg: Foreground color (0-255) or None
        bg: Background color (0-255) or None

    Returns:
        ANSI escape sequence for the colors
    """
    if fg is None and bg is None:
        return ""

    codes = []
    if fg is not None:
        codes.append(f"38;5;{fg}")
    if bg is not None:
        codes.append(f"48;5;{bg}")

    return f"\033[{';'.join(codes)}m"


@lru_cache(maxsize=512)
def get_rgb_code(fg_rgb: Optional[Tuple[int, int, int]] = None, bg_rgb: Optional[Tuple[int, int, int]] = None) -> str:
    """
    Generate ANSI color code for RGB colors.

    Args:
        fg_rgb: Foreground RGB tuple (r, g, b) or None
        bg_rgb: Background RGB tuple (r, g, b) or None

    Returns:
        ANSI escape sequence for the RGB colors
    """
    if fg_rgb is None and bg_rgb is None:
        return ""

    codes = []
    if fg_rgb is not None:
        r, g, b = fg_rgb
        codes.append(f"38;2;{r};{g};{b}")
    if bg_rgb is not None:
        r, g, b = bg_rgb
        codes.append(f"48;2;{r};{g};{b}")

    return f"\033[{';'.join(codes)}m"


@lru_cache(maxsize=256)
def get_style_code(
    bold: bool = False,
    dim: bool = False,
    italic: bool = False,
    underline: bool = False,
    blink: bool = False,
    reverse: bool = False,
    strike: bool = False,
    conceal: bool = False,
) -> str:
    """
    Generate ANSI style code for text attributes.

    Returns:
        ANSI escape sequence for the styles
    """
    codes = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if italic:
        codes.append("3")
    if underline:
        codes.append("4")
    if blink:
        codes.append("5")
    if reverse:
        codes.append("7")
    if conceal:
        codes.append("8")
    if strike:
        codes.append("9")

    if not codes:
        return ""

    return f"\033[{';'.join(codes)}m"


@lru_cache(maxsize=2048)
def get_combined_code(
    fg: Optional[int] = None,
    bg: Optional[int] = None,
    fg_rgb: Optional[Tuple[int, int, int]] = None,
    bg_rgb: Optional[Tuple[int, int, int]] = None,
    bold: bool = False,
    dim: bool = False,
    italic: bool = False,
    underline: bool = False,
    blink: bool = False,
    reverse: bool = False,
    strike: bool = False,
    conceal: bool = False,
) -> str:
    """
    Generate a combined ANSI code for colors and styles.

    This is the main function to use for complete styling.
    RGB colors take precedence over palette colors.

    Returns:
        Complete ANSI escape sequence or empty string
    """
    codes = []

    # Style attributes first
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if italic:
        codes.append("3")
    if underline:
        codes.append("4")
    if blink:
        codes.append("5")
    if reverse:
        codes.append("7")
    if conceal:
        codes.append("8")
    if strike:
        codes.append("9")

    # Colors (RGB takes precedence)
    if fg_rgb is not None:
        r, g, b = fg_rgb
        codes.append(f"38;2;{r};{g};{b}")
    elif fg is not None:
        codes.append(f"38;5;{fg}")

    if bg_rgb is not None:
        r, g, b = bg_rgb
        codes.append(f"48;2;{r};{g};{b}")
    elif bg is not None:
        codes.append(f"48;5;{bg}")

    if not codes:
        return ""

    return f"\033[{';'.join(codes)}m"


@lru_cache(maxsize=1)
def reset_code() -> str:
    """Get the ANSI reset code."""
    return "\033[0m"


@lru_cache(maxsize=16)
def get_basic_color_code(color: int, is_bg: bool = False) -> str:
    """
    Generate ANSI code for basic 16 colors (0-15).

    Args:
        color: Color index (0-7 for normal, 8-15 for bright)
        is_bg: True for background, False for foreground

    Returns:
        ANSI escape sequence
    """
    if 0 <= color <= 7:
        # Normal colors
        code = 40 + color if is_bg else 30 + color
    elif 8 <= color <= 15:
        # Bright colors
        code = 100 + (color - 8) if is_bg else 90 + (color - 8)
    else:
        return ""

    return f"\033[{code}m"


@lru_cache(maxsize=1)
def get_cursor_code() -> str:
    """Get ANSI code for cursor display (reverse video)."""
    return "\033[7m"


@lru_cache(maxsize=1)
def get_clear_line_code() -> str:
    """Get ANSI code to clear to end of line."""
    return "\033[K"


@lru_cache(maxsize=1)
def reset_foreground_code() -> str:
    """Get ANSI code to reset foreground color only."""
    return "\033[39m"


@lru_cache(maxsize=1)
def reset_background_code() -> str:
    """Get ANSI code to reset background color only."""
    return "\033[49m"


@lru_cache(maxsize=1)
def reset_text_attributes() -> str:
    """Reset text attributes but preserve background color."""
    return "\033[0;22;23;24;25;27;28;29;39m"
