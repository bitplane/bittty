"""
bittty: A fast, pure Python terminal emulator library.

bittty (bitplane-tty) is a high-performance terminal emulator engine
that provides comprehensive ANSI sequence parsing and terminal state management.
"""

from .terminal import Terminal
from .buffer import Buffer
from .parser import Parser
from .color import (
    get_color_code,
    get_rgb_code,
    get_style_code,
    get_combined_code,
    reset_code,
    get_cursor_code,
    get_clear_line_code,
)

__version__ = "0.1.0"

__all__ = [
    "Terminal",
    "Buffer",
    "Parser",
    "get_color_code",
    "get_rgb_code",
    "get_style_code",
    "get_combined_code",
    "reset_code",
    "get_cursor_code",
    "get_clear_line_code",
]
