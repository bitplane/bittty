"""
This module provides access to terminal capabilities from the terminfo database.
"""

from __future__ import annotations

from typing import Dict, Any


class TermInfo:
    """
    Stores and provides access to a terminal's capabilities from terminfo.
    """

    def __init__(self, term_name: str, overrides: str):
        """
        Initializes the terminal definition.

        This loads the capabilities for the given terminal name from the system's
        terminfo database and then applies any user-provided overrides.

        Args:
            term_name: The terminal name (e.g., "xterm-256color").
            overrides: A string of user-defined overrides, like in tmux.conf.
        """
        self.name: str = term_name
        self.capabilities: Dict[str, Any] = {}  # Populated by _read_terminfo
        self._read_terminfo(term_name)
        self._apply_overrides(overrides)

    def _read_terminfo(self, term_name: str) -> None:
        """
        Loads capabilities from the system terminfo database.

        This is a complex method that will likely need to use the `curses`
        module (`curses.setupterm`, `curses.tigetstr`, etc.) to read the raw
        terminfo data.
        """
        pass

    def _apply_overrides(self, overrides: str) -> None:
        """
        Parses and applies user overrides to the loaded capabilities.
        """
        pass

    def has(self, cap: str) -> bool:
        """
        Checks if the terminal has a given capability.
        """
        pass

    def get_string(self, cap: str) -> str:
        """
        Gets a string capability.

        This is the primary method for retrieving key codes (e.g., "kcuu1" for
        up arrow) to send to the child application.
        """
        pass

    def get_number(self, cap: str) -> int:
        """
        Gets a numeric capability.
        """
        pass

    def get_flag(self, cap: str) -> bool:
        """
        Gets a boolean flag capability.
        """
        pass

    def describe(self) -> str:
        """
        Returns a descriptive string of all loaded capabilities for debugging.
        """
        pass
