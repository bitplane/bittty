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


class BitTTY(Board):
    """The main terminal emulator chassis/motherboard.

    BitTTY is the main board that devices attach to. It coordinates all
    terminal operations and handles the core parsing of incoming byte
    streams into commands.

    Unlike the old monolithic Terminal class, BitTTY is lightweight and
    delegates all actual functionality to attached devices.
    """

    def __init__(self):
        """Initialize the BitTTY chassis/motherboard and parser."""
        super().__init__()
        self.parser = Parser(self)

        logger.info("BitTTY chassis initialized")

    def attach(self, component: "Device | Board") -> None:
        """Attach a device or board to the chassis.

        This is the primary way to add functionality to the terminal.
        Common devices include:
        - MonitorDevice: For screen display
        - ConnectionDevice: For PTY management
        - InputDevice: For keyboard/mouse handling
        - BellDevice: For notifications

        Args:
            component: The device or board to attach
        """
        super().attach(component)
        if hasattr(component, "__class__"):
            logger.info(f"Attached {component.__class__.__name__} to BitTTY")

    def dispatch(self, command: "Command") -> "Command | None":
        """Route command through attached devices.

        This is the main command dispatch point. Commands that
        aren't handled by any device are logged as unsupported.

        Args:
            command: The command to dispatch

        Returns:
            None if command was consumed, otherwise the command
        """
        result = super().dispatch(command)
        if result is not None:
            logger.debug(f"Unsupported command: {command}")
        return result

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

    def input(self, data: str) -> None:
        """Send input to the terminal process.

        Args:
            data: Input data to send
        """
        input_cmd = Command("SEND_INPUT", "INTERNAL", (data,), None)
        self.dispatch(input_cmd)

    def input_key(self, char: str, modifier: int = 1) -> None:
        """Send a key with modifiers to the terminal process.

        Args:
            char: The character
            modifier: Key modifier (1=none, 2=shift, 4=alt, 8=ctrl, etc.)
        """
        input_cmd = Command("SEND_INPUT_KEY", "INTERNAL", (char, str(modifier)), None)
        self.dispatch(input_cmd)

    def send(self, data: str) -> None:
        """Send data to terminal without flushing.

        Args:
            data: Data to send
        """
        self.input(data)

    def respond(self, data: str) -> None:
        """Send response data to terminal with flush.

        Args:
            data: Response data to send
        """
        respond_cmd = Command("SEND_RESPONSE", "INTERNAL", (data,), None)
        self.dispatch(respond_cmd)

    def query(self, feature_name: str) -> list:
        """Query all devices for a capability.

        This provides a way to discover what capabilities are
        available from the currently plugged-in devices.

        Args:
            feature_name: The capability to query

        Returns:
            List of capability values from supporting devices
        """
        return self.query_devices(feature_name)

    def get_devices(self, device_type: type | None = None) -> list[Device]:
        """Get all devices of a specific type.

        Args:
            device_type: The type of device to find, or None for all devices

        Returns:
            List of matching devices
        """
        if device_type is None:
            return list(self.devices)

        return [device for device in self.devices if isinstance(device, device_type)]

    def shutdown(self) -> None:
        """Shutdown the terminal and clean up resources.

        This should be called when the terminal is no longer needed
        to properly clean up any resources held by devices.
        """
        logger.info("Shutting down BitTTY")

        # Give devices a chance to clean up
        for device in self.devices:
            if hasattr(device, "cleanup"):
                try:
                    device.cleanup()
                except Exception as e:
                    logger.error(f"Error cleaning up {device.__class__.__name__}: {e}")

    def __repr__(self) -> str:
        """Return a string representation of the BitTTY instance."""
        device_names = [device.__class__.__name__ for device in self.devices]
        return f"BitTTY(devices={device_names})"
