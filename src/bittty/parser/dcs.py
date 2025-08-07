"""DCS (Device Control String) sequence handlers.

Handles DCS sequences that start with ESC P. These are used for device-specific
commands like sixel graphics, but current implementation is minimal.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..terminal import Terminal

logger = logging.getLogger(__name__)


def dispatch_dcs(terminal: Terminal, string_buffer: str) -> None:
    """Main DCS dispatcher.

    Currently minimal implementation - primarily used for passthrough sequences
    like tmux or for potential future sixel graphics support.
    """
    if not string_buffer:
        return

    # Currently we just consume DCS sequences without implementing them
    # This prevents them from leaking through to terminal output

    # Future implementation could handle:
    # - Sixel graphics (if enabled)
    # - Tmux passthrough sequences
    # - Other device-specific commands

    logger.debug(f"DCS sequence received (not implemented): {string_buffer[:50]}...")
