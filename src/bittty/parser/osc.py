"""OSC (Operating System Command) sequence handlers.

Handles OSC sequences that start with ESC]. These include window title operations,
color palette changes, and other system-level commands.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Callable

if TYPE_CHECKING:
    from ..terminal import Terminal

from .. import constants

logger = logging.getLogger(__name__)


def handle_set_title_and_icon(terminal: Terminal, data: str) -> None:
    """OSC 0 - Set both window title and icon title."""
    terminal.set_title(data)
    terminal.set_icon_title(data)


def handle_set_icon_title(terminal: Terminal, data: str) -> None:
    """OSC 1 - Set icon title only."""
    terminal.set_icon_title(data)


def handle_set_title(terminal: Terminal, data: str) -> None:
    """OSC 2 - Set window title only."""
    terminal.set_title(data)


def handle_set_color_palette(terminal: Terminal, data: str) -> None:
    """OSC 4 - Set color palette entry."""
    # Format: 4;index;color
    # TODO: Implement color palette setting if needed
    pass


def handle_set_cwd_url(terminal: Terminal, data: str) -> None:
    """OSC 7 - Set current working directory/URL."""
    # Format: 7;file://hostname/path
    # TODO: Implement if needed for directory tracking
    pass


def handle_hyperlink(terminal: Terminal, data: str) -> None:
    """OSC 8 - Define hyperlink."""
    # Format: 8;params;uri
    # TODO: Implement hyperlink support if needed
    pass


def handle_query_set_fg_color(terminal: Terminal, data: str) -> None:
    """OSC 10 - Query or set default foreground color."""
    if data == "?":
        # Query mode - respond with current foreground color
        # Default to white (rgb:ffff/ffff/ffff)
        terminal.respond("\033]10;rgb:ffff/ffff/ffff\007")
    else:
        # TODO: Handle setting foreground color if needed
        pass


def handle_query_set_bg_color(terminal: Terminal, data: str) -> None:
    """OSC 11 - Query or set default background color."""
    if data == "?":
        # Query mode - respond with current background color
        # Default to black (rgb:0000/0000/0000)
        terminal.respond("\033]11;rgb:0000/0000/0000\007")
    else:
        # TODO: Handle setting background color if needed
        pass


def handle_set_cursor_color(terminal: Terminal, data: str) -> None:
    """OSC 12 - Set cursor color."""
    # TODO: Implement cursor color setting if needed
    pass


def handle_clipboard(terminal: Terminal, data: str) -> None:
    """OSC 52 - Set/query clipboard content."""
    # Format: 52;selection;data
    # TODO: Implement clipboard operations if needed
    pass


def handle_reset_color_palette(terminal: Terminal, data: str) -> None:
    """OSC 104 - Reset color palette entry."""
    # TODO: Implement color palette reset if needed
    pass


def handle_reset_fg_color(terminal: Terminal, data: str) -> None:
    """OSC 110 - Reset default foreground color."""
    # TODO: Implement if needed
    pass


def handle_reset_bg_color(terminal: Terminal, data: str) -> None:
    """OSC 111 - Reset default background color."""
    # TODO: Implement if needed
    pass


def handle_reset_cursor_color(terminal: Terminal, data: str) -> None:
    """OSC 112 - Reset cursor color."""
    # TODO: Implement if needed
    pass


# OSC dispatch table - maps command numbers to handler functions
OSC_DISPATCH_TABLE: Dict[int, Callable[[Terminal, str], None]] = {
    constants.OSC_SET_TITLE_AND_ICON: handle_set_title_and_icon,  # 0
    constants.OSC_SET_ICON_TITLE: handle_set_icon_title,  # 1
    constants.OSC_SET_TITLE: handle_set_title,  # 2
    4: handle_set_color_palette,  # 4 - Set color palette
    7: handle_set_cwd_url,  # 7 - Set CWD URL
    8: handle_hyperlink,  # 8 - Hyperlinks
    constants.OSC_SET_DEFAULT_FG_COLOR: handle_query_set_fg_color,  # 10
    constants.OSC_SET_DEFAULT_BG_COLOR: handle_query_set_bg_color,  # 11
    constants.OSC_SET_CURSOR_COLOR: handle_set_cursor_color,  # 12
    52: handle_clipboard,  # 52 - Clipboard
    104: handle_reset_color_palette,  # 104 - Reset palette
    110: handle_reset_fg_color,  # 110 - Reset fg
    111: handle_reset_bg_color,  # 111 - Reset bg
    112: handle_reset_cursor_color,  # 112 - Reset cursor
}


# Global cache for OSC command parsing - provides speedup for repeated commands
_OSC_CACHE = {}
_OSC_CACHE_MAX_SIZE = 500  # Smaller than CSI cache since OSC sequences are less frequent


def dispatch_osc(terminal: Terminal, string_buffer: str) -> None:
    """BLAZING FAST OSC dispatcher with caching! 🚀

    Optimizations:
    1. **Caching**: Parse results for repeated OSC commands (window titles repeat)
    2. **Fast paths**: Handle common OSC commands with minimal processing
    3. **Reduced allocations**: Cache parsed command numbers and data splits
    """
    global _OSC_CACHE

    if not string_buffer:
        return

    # Periodic cache cleanup to prevent memory leaks
    if len(_OSC_CACHE) > _OSC_CACHE_MAX_SIZE:
        _OSC_CACHE.clear()

    # Cache lookup for repeated OSC sequences
    if string_buffer in _OSC_CACHE:
        cmd, data = _OSC_CACHE[string_buffer]
    else:
        # ⚡ FAST PATH: Check for common simple patterns first
        # Pattern: "0;title" or "2;title" (extremely common for window titles)
        if len(string_buffer) > 2 and string_buffer[1] == ";" and string_buffer[0].isdigit():
            cmd = int(string_buffer[0])
            data = string_buffer[2:]
            _OSC_CACHE[string_buffer] = (cmd, data)
        # Pattern: "10;color" or "11;color" (common for colors)
        elif len(string_buffer) > 3 and string_buffer[2] == ";" and string_buffer[:2].isdigit():
            cmd = int(string_buffer[:2])
            data = string_buffer[3:]
            _OSC_CACHE[string_buffer] = (cmd, data)
        else:
            # Complex parsing needed (less common)
            cmd, data = _parse_osc_complex(string_buffer)
            if cmd is not None:
                _OSC_CACHE[string_buffer] = (cmd, data)
            else:
                return  # Invalid sequence

    # Use dispatch table for O(1) lookup
    handler = OSC_DISPATCH_TABLE.get(cmd)
    if handler:
        handler(terminal, data)
    else:
        # Unknown OSC command - log and consume
        logger.debug(f"Unknown OSC command: {cmd} with data: {data}")
        # We still consume the sequence to prevent it from leaking through


def _parse_osc_complex(string_buffer: str) -> tuple[int, str]:
    """Handle complex OSC parsing that needs full string splitting."""
    # Parse OSC command: number;data
    parts = string_buffer.split(";", 1)
    if len(parts) < 1:
        return None, ""

    try:
        cmd = int(parts[0])
    except ValueError:
        logger.debug(f"Invalid OSC command number: {parts[0]}")
        return None, ""

    # Get data part (everything after first semicolon)
    data = parts[1] if len(parts) >= 2 else ""

    return cmd, data
