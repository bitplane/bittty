"""TTY Input device for host terminal input handling.

This device represents the physical TTY terminal we're running inside.
It handles setting raw mode, reading from stdin, and translating
host terminal sequences into commands for the child process.
"""

from __future__ import annotations

import os
import sys
import termios
import tty
import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ..command import Command

from .input import InputDevice
from .. import constants
from ..command import create_internal_command

logger = logging.getLogger(__name__)


class TTYInputDevice(InputDevice):
    """Input device that represents the host TTY terminal.

    This device handles:
    - Setting the host terminal to raw mode
    - Reading keystrokes from sys.stdin
    - Translating host terminal sequences to child process input
    - Querying host terminal input capabilities
    """

    def __init__(self, board=None):
        """Initialize the TTY input device."""
        super().__init__(board)

        self.old_termios = None
        self.raw_mode_active = False

        # Get terminal name from environment
        self.term_name = os.environ.get("TERM", "xterm")

        logger.debug(f"TTYInputDevice initialized for terminal: {self.term_name}")

    def get_command_handlers(self):
        """Return the commands this TTY input device handles."""
        handlers = super().get_command_handlers()
        handlers.update(
            {
                # TTY-specific commands
                "TTY_SETUP": self.handle_tty_setup,
                "TTY_CLEANUP": self.handle_tty_cleanup,
                "TTY_READ_INPUT": self.handle_tty_read_input,
            }
        )
        return handlers

    def query(self, feature_name: str) -> Any:
        """Query TTY input capabilities."""
        if feature_name == "terminal_name":
            return self.term_name
        elif feature_name == "raw_mode":
            return self.raw_mode_active
        elif feature_name == "stdin_isatty":
            return sys.stdin.isatty()
        return super().query(feature_name)

    def setup_raw_mode(self) -> None:
        """Set the host terminal to raw mode for proper input handling."""
        if not sys.stdin.isatty():
            logger.warning("stdin is not a TTY, cannot set raw mode")
            return

        try:
            self.old_termios = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())
            self.raw_mode_active = True
            logger.debug("Set host terminal to raw mode")
        except (OSError, termios.error) as e:
            logger.error(f"Failed to set raw mode: {e}")

    def restore_terminal(self) -> None:
        """Restore the host terminal to its original settings."""
        if self.old_termios and sys.stdin.isatty():
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_termios)
                self.raw_mode_active = False
                logger.debug("Restored host terminal settings")
            except (OSError, termios.error) as e:
                logger.error(f"Failed to restore terminal: {e}")

    def read_input_char(self) -> Optional[str]:
        """Read a single character from stdin.

        Returns:
            The character read, or None if no data available
        """
        if not sys.stdin.isatty() or not self.raw_mode_active:
            return None

        try:
            data = os.read(sys.stdin.fileno(), 1)
            return data.decode("utf-8", errors="replace")
        except (OSError, BlockingIOError):
            return None

    def handle_tty_setup(self, command: "Command") -> None:
        """Handle TTY setup command."""
        self.setup_raw_mode()
        return None

    def handle_tty_cleanup(self, command: "Command") -> None:
        """Handle TTY cleanup command."""
        self.restore_terminal()
        return None

    def handle_tty_read_input(self, command: "Command") -> None:
        """Handle reading input from TTY."""
        char = self.read_input_char()
        if char:
            # Process the character and send to connection
            self.process_input_char(char)
        return None

    def process_input_char(self, char: str) -> None:
        """Process a character from the host terminal and send to child process."""
        # Handle special key combinations
        char_code = ord(char)

        if char_code == 3:  # Ctrl+C
            self.send_input_key("c", constants.KEY_MOD_CTRL)
        elif char_code == 4:  # Ctrl+D (EOF)
            self.send_input(char)
        elif char_code == 27:  # ESC - might be escape sequence
            # For now, send ESC directly
            # A full implementation would parse multi-byte escape sequences
            self.send_input(char)
        else:
            # Regular character
            self.send_input(char)

    def send_input(self, data: str) -> None:
        """Send input data to the connection device."""
        if self.board:
            # Create a command to send input to the connection
            input_cmd = create_internal_command("SEND_INPUT", data)
            self.board.dispatch(input_cmd)

    def send_input_key(self, char: str, modifier: int = constants.KEY_MOD_NONE) -> None:
        """Send a key with modifiers to the connection device."""
        if self.board:
            # Create a command to send key input to the connection
            input_cmd = create_internal_command("SEND_INPUT_KEY", char, str(modifier))
            self.board.dispatch(input_cmd)

    def cleanup(self) -> None:
        """Clean up the TTY input device."""
        self.restore_terminal()
