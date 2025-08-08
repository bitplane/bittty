"""
bittty: A fast, pure Python terminal emulator library.

bittty (bitplane-tty) is a high-performance terminal emulator engine
that provides comprehensive ANSI sequence parsing and terminal state management.

The new architecture includes:
- BitTTY: Hardware-inspired modular terminal emulator
- Devices: Pluggable components (Monitor, Connection, Bell, etc.)
- Commands: Lightweight messages for terminal operations

For backward compatibility, the original Terminal class is still available.
"""

# New modular architecture
from .bittty import BitTTY
from .device import Device, Board
from .command import Command, command_to_escape
from . import devices

# Legacy architecture (for backward compatibility)
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

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("bittty")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = [
    # New architecture
    "BitTTY",
    "Device",
    "Board",
    "Command",
    "command_to_escape",
    "devices",
    # Legacy architecture
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
