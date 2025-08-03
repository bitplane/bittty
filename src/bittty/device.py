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
            board.plug_in(self)

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

    def handle_command(self, cmd: Command) -> Command | None:
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

    def get_command_handlers(self) -> dict[str, Callable[[Command], Command | None]]:
        """What commands this device wants to handle.

        Returns a mapping of command names to handler functions.
        The board uses this to build its dispatch table.

        Returns:
            Dictionary mapping command names to handler functions
        """
        return {}

    def dispatch_to_board(self, command: Command) -> Command | None:
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

    def plug_in(self, device: Device) -> None:
        """Plug a device into this board.

        This registers the device and builds the dispatch table
        based on what commands the device handles.

        Args:
            device: The device to plug in
        """
        self.devices.append(device)
        device.board = self

        # Build dispatch table
        handlers = device.get_command_handlers()
        for cmd_name, handler in handlers.items():
            if cmd_name not in self.dispatch_table:
                self.dispatch_table[cmd_name] = []
            self.dispatch_table[cmd_name].append(handler)

        logger.debug(f"Plugged {device.__class__.__name__} into board, handles: {list(handlers.keys())}")

    def plug_in_board(self, board: Board) -> None:
        """Plug another board into this one (expansion slot).

        This creates a BoardDevice wrapper to make the board
        look like a device for nesting purposes.

        Args:
            board: The board to plug in as an expansion
        """
        board_device = BoardDevice(board)
        self.plug_in(board_device)

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


class BoardDevice(Device):
    """Wrapper to make a Board look like a Device for nesting.

    This allows boards to be plugged into other boards,
    creating a hierarchical structure like hardware expansion slots.
    """

    def __init__(self, board: Board):
        """Wrap a board to make it look like a device.

        Args:
            board: The board to wrap
        """
        self.wrapped_board = board
        super().__init__(None)  # Don't auto-register

    def get_command_handlers(self) -> dict[str, Callable[[Command], Command | None]]:
        """Return all command handlers from the wrapped board.

        This allows the dispatch table to be built correctly
        for all devices on the wrapped board.
        """
        handlers = {}
        for device in self.wrapped_board.devices:
            device_handlers = device.get_command_handlers()
            for cmd_name, handler in device_handlers.items():
                if cmd_name not in handlers:
                    handlers[cmd_name] = []
                if not isinstance(handlers[cmd_name], list):
                    handlers[cmd_name] = [handlers[cmd_name]]
                handlers[cmd_name].append(handler)

        # Return a flattened handler that dispatches to the board
        result = {}
        for cmd_name in handlers:
            result[cmd_name] = lambda cmd, b=self.wrapped_board: b.dispatch(cmd)

        return result

    def handle_command(self, cmd: Command) -> Command | None:
        """Forward command to the wrapped board.

        Args:
            cmd: The command to forward

        Returns:
            The result from the wrapped board's dispatch
        """
        return self.wrapped_board.dispatch(cmd)

    def query(self, feature_name: str) -> Any:
        """Forward capability query to the wrapped board.

        Args:
            feature_name: The capability to query

        Returns:
            List of results from the wrapped board's devices
        """
        results = self.wrapped_board.query_devices(feature_name)
        return results if results else None
