"""Printer device for line-oriented output.

This device handles line-oriented output similar to teletype printers,
including print modes, form feeds, and line-based operations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..command import Command

from ..device import Device

logger = logging.getLogger(__name__)


class PrinterDevice(Device):
    """A printer device that handles line-oriented output.

    This device emulates a teletype printer or line printer,
    handling operations like form feeds, vertical tabs,
    and print-related control codes.
    """

    def __init__(self, width: int = 80, board=None):
        """Initialize the printer device.

        Args:
            width: Line width in characters
            board: Board to plug into
        """
        super().__init__(board)

        self.width = width
        self.page_position = 0
        self.line_position = 0

        # Print modes
        self.print_mode = False  # Whether in print mode

        logger.debug(f"PrinterDevice initialized with width: {width}")

    def get_command_handlers(self):
        """Return the commands this printer device handles."""
        return {
            # Line-oriented commands
            "C0_FF": self.handle_form_feed,  # Form Feed
            "C0_VT": self.handle_vertical_tab,  # Vertical Tab
            # Print-related commands (future expansion)
            # 'PRINT_SCREEN': self.handle_print_screen,
            # 'PRINT_LINE': self.handle_print_line,
        }

    def query(self, feature_name: str) -> Any:
        """Query printer capabilities."""
        if feature_name == "printer_width":
            return self.width
        elif feature_name == "page_position":
            return self.page_position
        elif feature_name == "print_mode":
            return self.print_mode
        return None

    def handle_form_feed(self, command: "Command") -> None:
        """Handle form feed - advance to next page."""
        self.page_position += 1
        self.line_position = 0
        logger.debug(f"Form feed - page {self.page_position}")
        return None

    def handle_vertical_tab(self, command: "Command") -> None:
        """Handle vertical tab - advance to next tab stop."""
        # For now, just advance one line
        self.line_position += 1
        logger.debug(f"Vertical tab - line {self.line_position}")
        return None


class LinePrinter(PrinterDevice):
    """A line printer device (like an ASR-33 teletype)."""

    def __init__(self, width: int = 72, uppercase_only: bool = False, board=None):
        """Initialize the line printer.

        Args:
            width: Line width in characters
            uppercase_only: Whether to convert text to uppercase
            board: Board to plug into
        """
        super().__init__(width, board)
        self.uppercase_only = uppercase_only

    def get_command_handlers(self):
        """Return the commands this line printer handles."""
        handlers = super().get_command_handlers()
        handlers.update(
            {
                "TEXT": self.handle_text,
                "C0_CR": self.handle_carriage_return,
                "C0_LF": self.handle_line_feed,
            }
        )
        return handlers

    def handle_text(self, command: "Command") -> None:
        """Handle text printing."""
        if command.args:
            text = command.args[0]
            if self.uppercase_only:
                text = text.upper()

            # Simulate printing text
            logger.debug(f"Line printer: {text}")
            self.line_position += len(text)

            # Handle line wrapping
            if self.line_position >= self.width:
                self.line_position = 0

        return None

    def handle_carriage_return(self, command: "Command") -> None:
        """Handle carriage return."""
        self.line_position = 0
        return None

    def handle_line_feed(self, command: "Command") -> None:
        """Handle line feed."""
        # Advance paper one line
        logger.debug("Line printer: line feed")
        return None
