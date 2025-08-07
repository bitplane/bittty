"""Parser module for terminal escape sequence processing.

This module provides a modular parser system that processes terminal escape sequences
through specialized handlers:

- CSI sequences (cursor movement, styling, modes)
- OSC sequences (window titles, colors)
- Simple escape sequences (cursor save/restore, etc.)
- DCS sequences (device control strings)

The main Parser class coordinates all these handlers and maintains the state machine.
"""

from .core import Parser, parse_string_sequence

__all__ = ["Parser", "parse_string_sequence"]
