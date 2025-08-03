"""BitTTY - A hardware-inspired terminal emulator.

BitTTY is designed as a "metal box" - a central hub that mirrors the architecture
of hardware terminals. Components are attached to provide specific functionality,
just like adding cards or peripherals to physical terminal hardware.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .command import Command
    from .device import Device, Board

from .device import Board
from .command_parser import Parser

logger = logging.getLogger(__name__)


class BitTTY:
    """The main terminal emulator chassis.

    BitTTY acts as the "metal box" that coordinates all terminal operations.
    It contains the main board for device registration and handles the core
    parsing of incoming byte streams into commands.

    Unlike the old monolithic Terminal class, BitTTY is lightweight and
    delegates all actual functionality to plugged-in devices.
    """

    def __init__(self):
        """Initialize the BitTTY chassis with a main board and parser."""
        self.main_board = Board()
        self.parser = Parser(self)

        logger.info("BitTTY chassis initialized")

    def plug_in(self, device: Device) -> None:
        """Plug a device into the main board.

        This is the primary way to add functionality to the terminal.
        Common devices include:
        - MonitorDevice: For screen display
        - ConnectionDevice: For PTY management
        - InputDevice: For keyboard/mouse handling
        - BellDevice: For notifications

        Args:
            device: The device to plug in
        """
        self.main_board.plug_in(device)
        logger.info(f"Plugged {device.__class__.__name__} into main board")

    def plug_in_board(self, board: Board) -> None:
        """Plug an expansion board into the main board.

        This allows creating hierarchical device structures,
        like having specialized boards for input, output, etc.

        Args:
            board: The expansion board to plug in
        """
        self.main_board.plug_in_board(board)
        logger.info("Plugged expansion board into main board")

    def dispatch(self, command: Command) -> None:
        """Route command through the board hierarchy.

        This is the main command dispatch point. Commands that
        aren't handled by any device are logged as unsupported.

        Args:
            command: The command to dispatch
        """
        result = self.main_board.dispatch(command)
        if result is not None:
            logger.debug(f"Unsupported command: {command}")

    def feed(self, data: str | bytes) -> None:
        """Feed data to the parser for processing.

        This is the main entry point for terminal data. The parser
        will convert the byte stream into commands and dispatch them.

        Args:
            data: Raw terminal data (bytes or string)
        """
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8", errors="replace")
            except UnicodeDecodeError:
                logger.warning("Failed to decode input data")
                return

        self.parser.feed(data)

    def query(self, feature_name: str) -> list:
        """Query all devices for a capability.

        This provides a way to discover what capabilities are
        available from the currently plugged-in devices.

        Args:
            feature_name: The capability to query

        Returns:
            List of capability values from supporting devices
        """
        return self.main_board.query_devices(feature_name)

    def get_devices(self, device_type: type | None = None) -> list[Device]:
        """Get all devices of a specific type.

        Args:
            device_type: The type of device to find, or None for all devices

        Returns:
            List of matching devices
        """
        if device_type is None:
            return list(self.main_board.devices)

        return [device for device in self.main_board.devices if isinstance(device, device_type)]

    def shutdown(self) -> None:
        """Shutdown the terminal and clean up resources.

        This should be called when the terminal is no longer needed
        to properly clean up any resources held by devices.
        """
        logger.info("Shutting down BitTTY")

        # Give devices a chance to clean up
        # We'll add a cleanup method to Device interface later if needed
        for device in self.main_board.devices:
            if hasattr(device, "cleanup"):
                try:
                    device.cleanup()
                except Exception as e:
                    logger.error(f"Error cleaning up {device.__class__.__name__}: {e}")

    def __repr__(self) -> str:
        """Return a string representation of the BitTTY instance."""
        device_names = [device.__class__.__name__ for device in self.main_board.devices]
        return f"BitTTY(devices={device_names})"
