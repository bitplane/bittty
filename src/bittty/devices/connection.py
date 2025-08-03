"""Connection device for PTY and process management.

This device handles the connection to the actual process being emulated,
including PTY management, process spawning, and I/O operations.
"""

from __future__ import annotations

import sys
import asyncio
import subprocess
import logging
from typing import TYPE_CHECKING, Any, Optional, Callable

if TYPE_CHECKING:
    from ..command import Command

from ..device import Device
from .. import constants

logger = logging.getLogger(__name__)


class ConnectionDevice(Device):
    """A connection device that manages PTY and process I/O.

    This device handles the connection to the actual process,
    similar to how a serial port or PTY connection works in
    hardware terminals.
    """

    def __init__(self, command: str = "/bin/bash", board=None):
        """Initialize the connection device.

        Args:
            command: The command to run in the PTY
            board: Board to plug into
        """
        super().__init__(board)

        self.command = command

        # Process management
        self.process: Optional[subprocess.Popen] = None
        self.pty: Optional[Any] = None
        self._pty_reader_task: Optional[asyncio.Task] = None

        # PTY data callback for async handling
        self._pty_data_callback: Optional[Callable[[str], None]] = None

        # Terminal size (will be updated by monitor devices)
        self.rows = constants.DEFAULT_TERMINAL_HEIGHT
        self.cols = constants.DEFAULT_TERMINAL_WIDTH

        logger.debug(f"ConnectionDevice initialized for command: {command}")

    @staticmethod
    def get_pty_handler(
        rows: int = constants.DEFAULT_TERMINAL_HEIGHT,
        cols: int = constants.DEFAULT_TERMINAL_WIDTH,
        stdin=None,
        stdout=None,
    ):
        """Create a platform-appropriate PTY handler."""
        if stdin is not None and stdout is not None:
            from ..pty import StdioPTY

            return StdioPTY(stdin, stdout, rows, cols)
        elif sys.platform == "win32":
            from ..pty import WindowsPTY

            return WindowsPTY(rows, cols)
        else:
            from ..pty import UnixPTY

            return UnixPTY(rows, cols)

    def get_command_handlers(self):
        """Return the commands this connection device handles."""
        return {
            # Internal commands for device communication
            "RESIZE_PTY": self.handle_resize_pty,
            "SEND_INPUT": self.handle_send_input,
            "SEND_INPUT_KEY": self.handle_send_input_key,
            "SEND_RESPONSE": self.handle_send_response,
            "SEND_MOUSE": self.handle_send_mouse,
            # Device queries and responses
            "CSI_DA": self.handle_device_attributes,  # Device Attributes
            "CSI_DSR": self.handle_device_status_report,  # Device Status Report
            # Application keypad mode (affects input encoding)
            "SET_KEYPAD_MODE": self.handle_set_keypad_mode,
        }

    def query(self, feature_name: str) -> Any:
        """Query connection capabilities."""
        if feature_name == "process_running":
            return self.process is not None and self.process.poll() is None
        elif feature_name == "pty_size":
            return (self.cols, self.rows)
        elif feature_name == "command":
            return self.command
        return None

    def set_pty_data_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for handling PTY data asynchronously."""
        self._pty_data_callback = callback

    def _process_pty_data_sync(self, data: str) -> None:
        """Process PTY data synchronously (fallback)."""
        if self.board:
            # Feed data back into the BitTTY system for parsing
            if hasattr(self.board, "bittty"):
                self.board.bittty.feed(data)

    def resize_pty(self, width: int, height: int) -> None:
        """Resize the PTY."""
        self.cols = width
        self.rows = height

        if self.pty:
            try:
                self.pty.resize(width, height)
                logger.debug(f"PTY resized to {width}x{height}")
            except Exception as e:
                logger.error(f"Failed to resize PTY: {e}")

    # Command handlers

    def handle_resize_pty(self, command: "Command") -> None:
        """Handle PTY resize command."""
        if len(command.args) >= 2:
            width = int(command.args[0])
            height = int(command.args[1])
            self.resize_pty(width, height)
        return None

    def handle_send_input(self, command: "Command") -> None:
        """Handle sending input to the PTY."""
        if command.args:
            data = command.args[0]
            self.send(data)
        return None

    def handle_send_input_key(self, command: "Command") -> None:
        """Handle sending a key with modifiers to the PTY."""
        if len(command.args) >= 2:
            char = command.args[0]
            modifier = int(command.args[1]) if command.args[1] else 1
            # Convert key to terminal sequence based on modifier
            key_data = self._encode_key_input(char, modifier)
            self.send(key_data)
        return None

    def handle_send_response(self, command: "Command") -> None:
        """Handle sending response data to the PTY with flush."""
        if command.args:
            data = command.args[0]
            self.send(data, flush=True)
        return None

    def handle_send_mouse(self, command: "Command") -> None:
        """Handle sending mouse data to the PTY."""
        if command.args:
            mouse_data = command.args[0]
            self.send(mouse_data)
        return None

    def handle_device_attributes(self, command: "Command") -> None:
        """Handle Device Attributes request."""
        # Respond with VT100 compatibility
        response = "\x1b[?1;2c"  # VT100 with AVO
        self.respond(response)
        return None

    def handle_device_status_report(self, command: "Command") -> None:
        """Handle Device Status Report."""
        if command.args:
            param = int(command.args[0])
            if param == 5:  # Status report
                self.respond("\x1b[0n")  # Terminal OK
            elif param == 6:  # Cursor position report
                # Need to get cursor position from monitor device
                cursor_pos = self.query_board("cursor_position")
                if cursor_pos:
                    x, y = cursor_pos[0] if cursor_pos else (1, 1)
                    # Convert to 1-based coordinates
                    self.respond(f"\x1b[{y+1};{x+1}R")
        return None

    def handle_set_keypad_mode(self, command: "Command") -> None:
        """Handle keypad mode setting."""
        if command.args:
            mode = command.args[0]
            # This affects how input devices encode keypad keys
            # We'll just store the mode for now
            self.application_keypad = mode == "application"
        return None

    def query_board(self, feature_name: str) -> list[Any]:
        """Query other devices on the board."""
        if self.board:
            return self.board.query_devices(feature_name)
        return []

    # PTY and process management

    def respond(self, data: str) -> None:
        """Send response data to the PTY with flush."""
        self.send(data, flush=True)

    def _send_to_pty(self, data: str, flush: bool = False) -> None:
        """Send data to the PTY."""
        if self.pty:
            try:
                data_bytes = data.encode("utf-8")
                self.pty.write(data_bytes)
                if flush:
                    self.pty.flush()
            except Exception as e:
                logger.error(f"Error writing to PTY: {e}")

    async def start_process(self, stdin=None, stdout=None) -> None:
        """Start the PTY process asynchronously."""
        try:
            # Create PTY handler
            self.pty = self.get_pty_handler(rows=self.rows, cols=self.cols, stdin=stdin, stdout=stdout)

            # Start the process
            self.process = self.pty.spawn_process(self.command)

            # Start reading from PTY
            self._pty_reader_task = asyncio.create_task(self._async_read_from_pty())

            logger.info(f"Process started: {self.command}")

        except Exception as e:
            logger.error(f"Failed to start process: {e}")
            raise

    def stop_process(self) -> None:
        """Stop the PTY process."""
        try:
            if self._pty_reader_task:
                self._pty_reader_task.cancel()
                self._pty_reader_task = None

            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                except Exception as e:
                    logger.error(f"Error stopping process: {e}")
                finally:
                    self.process = None

            if self.pty:
                self.pty.close()
                self.pty = None

            logger.info("Process stopped")

        except Exception as e:
            logger.error(f"Error stopping process: {e}")

    async def _async_read_from_pty(self) -> None:
        """Asynchronously read data from the PTY."""
        try:
            while self.pty and self.process and self.process.poll() is None:
                try:
                    data = await self.pty.read_async()
                    if data:
                        if self._pty_data_callback:
                            self._pty_data_callback(data)
                        else:
                            self._process_pty_data_sync(data)
                    else:
                        # No data available, small delay
                        await asyncio.sleep(0.01)

                except Exception as e:
                    logger.error(f"Error reading from PTY: {e}")
                    break

        except asyncio.CancelledError:
            logger.debug("PTY reader task cancelled")
        except Exception as e:
            logger.error(f"Unexpected error in PTY reader: {e}")
        finally:
            logger.debug("PTY reader task finished")

    def _encode_key_input(self, char: str, modifier: int) -> str:
        """Encode a key with modifiers into a terminal sequence."""
        from .. import constants

        if len(char) == 1:
            # Handle control characters
            if modifier & constants.KEY_MOD_CTRL:
                if "a" <= char.lower() <= "z":
                    # Convert to control character
                    return chr(ord(char.lower()) - ord("a") + 1)

            # For other modifiers, return the character as-is for now
            # A full implementation would handle function keys, arrow keys, etc.
            return char

        return char

    def send(self, data: str, flush: bool = False) -> None:
        """Send data to the PTY.

        Args:
            data: Data to send
            flush: Whether to flush immediately
        """
        if self.pty and not self.pty.closed:
            try:
                self.pty.write(data)
                if flush:
                    self.pty.flush()
                logger.debug(f"Sent to PTY: {repr(data)}")
            except Exception as e:
                logger.error(f"Failed to send to PTY: {e}")

    def cleanup(self) -> None:
        """Clean up resources when device is removed."""
        self.stop_process()
