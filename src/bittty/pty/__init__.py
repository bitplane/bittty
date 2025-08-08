"""
PTY implementations for terminal emulation.

This package provides platform-specific PTY implementations and a stdio
implementation for stream mode operations.
"""

import sys

from .base import PTYBase
from .stdio import StdioPTY

__all__ = ["PTYBase", "StdioPTY"]

if sys.platform == "win32":
    from .windows import WindowsPTY  # noqa: F401

    __all__.append("WindowsPTY")
else:
    from .unix import UnixPTY  # noqa: F401

    __all__.append("UnixPTY")
