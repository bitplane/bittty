"""Terminals: the chrome a human looks at, named by venue.

Kept in its own package so the board never imports terminal code —
the "board is never subclassed by a terminal" rule, enforced structurally.
"""

from .base import Terminal
from .stdio import StdioTerminal

__all__ = ["Terminal", "StdioTerminal"]
