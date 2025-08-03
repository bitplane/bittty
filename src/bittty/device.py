"""Device and Board infrastructure for the BitTTY terminal emulator.

Devices handle specific terminal functionality (like monitors, keyboards, etc.)
and plug into Boards which route commands between devices.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .command import Command

logger = logging.getLogger(__name__)


class Device:
    """A terminal device - handles specific functionality.

    Devices are modular components that handle specific aspects of terminal
    operation, such as:
    - MonitorDevice: Screen display, cursor movement, colors
    - ConnectionDevice: PTY management and process I/O
    - InputDevice: Keyboard and mouse input
    - BellDevice: Audio/visual notifications
    - PrinterDevice: Line-oriented output

    Devices can be plugged into Boards for command routing.
    """

    def __init__(self, board: Board | None = None):
        """Initialize the device and optionally plug into a board.

        Args:
            board: The board to plug this device into, if any
        """
        self.board = board
        if board:
            board.attach(self)

    def query(self, feature_name: str) -> Any:
        """Query device capabilities (terminfo-style).

        This allows other devices to discover what capabilities this
        device supports, similar to how terminfo works.

        Args:
            feature_name: The capability to query (e.g., 'colors', 'mouse')

        Returns:
            The capability value, or None if not supported
        """
        return None

    def handle_command(self, cmd: "Command") -> "Command | None":
        """Handle a command. Return None if consumed.

        This is the main entry point for command processing. Devices
        should check if they can handle the command and either:
        - Process it and return None (command consumed)
        - Return the command unchanged (not handled)
        - Return a modified command (command transformed)

        Args:
            cmd: The Command to handle

        Returns:
            None if command was consumed, otherwise the command (possibly modified)
        """
        handlers = self.get_command_handlers()
        handler = handlers.get(cmd.name)
        if handler:
            return handler(cmd)
        return cmd  # Not handled

    def get_command_handlers(self) -> dict[str, Callable[["Command"], "Command | None"]]:
        """What commands this device wants to handle.

        Returns a mapping of command names to handler functions.
        The board uses this to build its dispatch table.

        Returns:
            Dictionary mapping command names to handler functions
        """
        return {}

    def dispatch_to_board(self, command: "Command") -> "Command | None":
        """Send a command to other devices on the same board.

        This allows devices to communicate with each other by sending
        commands through the board's dispatch system.

        Args:
            command: The command to dispatch

        Returns:
            The result of the dispatch (None if consumed)
        """
        if self.board:
            return self.board.dispatch(command)
        return command


class Board:
    """A board that devices plug into - handles command routing.

    Boards route commands between the devices plugged into them.
    They maintain a dispatch table for efficient command routing
    and can be nested (boards can plug into other boards).
    """

    def __init__(self, parent_board: Board | None = None):
        """Initialize the board and optionally plug into a parent board.

        Args:
            parent_board: The parent board to plug this board into, if any
        """
        self.devices: list[Device] = []
        self.dispatch_table: dict[str, list[Callable[[Command], Command | None]]] = {}
        self.parent = parent_board

        if parent_board:
            parent_board.plug_in_board(self)

    def attach(self, component: Device | Board) -> None:
        """Attach a device or board to this board.

        This registers the component and builds the dispatch table
        based on what commands it handles.

        Args:
            component: The device or board to attach
        """
        if isinstance(component, Device):
            self._attach_device(component)
        elif isinstance(component, Board):
            self._attach_board(component)
        else:
            raise TypeError(f"Can only attach Device or Board, got {type(component)}")

    def _attach_device(self, device: Device) -> None:
        """Attach a device to this board."""
        self.devices.append(device)
        device.board = self

        # Build dispatch table
        handlers = device.get_command_handlers()
        for cmd_name, handler in handlers.items():
            if cmd_name not in self.dispatch_table:
                self.dispatch_table[cmd_name] = []
            self.dispatch_table[cmd_name].append(handler)

        logger.debug(f"Attached {device.__class__.__name__} to board, handles: {list(handlers.keys())}")

    def _attach_board(self, board: "Board") -> None:
        """Attach another board to this board."""
        # For now, we don't support board-to-board attachment
        raise NotImplementedError("Board-to-board attachment not yet supported")

    def dispatch(self, command: Command) -> Command | None:
        """Route command to devices.

        Commands are dispatched to all handlers that are registered
        for that command name. If any handler returns None, the
        command is considered consumed and dispatch stops.

        Args:
            command: The command to dispatch

        Returns:
            None if command was consumed, otherwise the command
        """
        # Try the dispatch table first (for performance)
        handlers = self.dispatch_table.get(command.name, [])

        for handler in handlers:
            try:
                result = handler(command)
                if result is None:  # Command consumed
                    logger.debug(f"Command {command.name} consumed by handler")
                    return None
                # Handler might have modified the command
                command = result
            except Exception as e:
                logger.error(f"Error in command handler for {command.name}: {e}")
                continue

        # If no registered handlers worked, try direct device dispatch
        # This handles dynamically added devices in sub-boards
        for device in self.devices:
            try:
                result = device.handle_command(command)
                if result is None:  # Command consumed
                    logger.debug(f"Command {command.name} consumed by {device.__class__.__name__}")
                    return None
                # Handler might have modified the command
                command = result
            except Exception as e:
                logger.error(f"Error in device {device.__class__.__name__} for {command.name}: {e}")
                continue

        # No handler consumed the command
        logger.debug(f"Command {command.name} not handled by any device")
        return command

    def query_devices(self, feature_name: str) -> list[Any]:
        """Query all devices for a capability.

        Args:
            feature_name: The capability to query

        Returns:
            List of capability values from devices that support it
        """
        results = []
        for device in self.devices:
            result = device.query(feature_name)
            if result is not None:
                results.append(result)
        return results
