"""Input device for keyboard and mouse handling.

This device handles input from keyboards, mice, and other input devices,
translating them into appropriate terminal input sequences.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..command import Command

from ..device import Device
from .. import constants
from ..command import create_internal_command

logger = logging.getLogger(__name__)


class InputDevice(Device):
    """Base input device for handling user input.

    This device translates user input (keyboard, mouse) into
    appropriate terminal sequences and sends them to the connection.
    """

    def __init__(self, board=None):
        """Initialize the input device.

        Args:
            board: Board to plug into
        """
        super().__init__(board)

        # Input modes
        self.application_keypad = False
        self.cursor_application_mode = False
        self.mouse_tracking = False
        self.mouse_button_tracking = False
        self.mouse_any_tracking = False
        self.mouse_sgr_mode = False
        self.mouse_extended_mode = False

        # Mouse position
        self.mouse_x = 0
        self.mouse_y = 0

        logger.debug("InputDevice initialized")

    def get_command_handlers(self):
        """Return the commands this input device handles."""
        return {
            # Mode setting commands that affect input
            "SET_KEYPAD_MODE": self.handle_set_keypad_mode,
            # Mouse tracking mode commands
            "ENABLE_MOUSE_TRACKING": self.handle_enable_mouse_tracking,
            "DISABLE_MOUSE_TRACKING": self.handle_disable_mouse_tracking,
            # Internal input commands
            "INPUT_KEY": self.handle_input_key,
            "INPUT_MOUSE": self.handle_input_mouse,
        }

    def query(self, feature_name: str) -> Any:
        """Query input capabilities."""
        if feature_name == "mouse_tracking":
            return self.mouse_tracking
        elif feature_name == "keypad_mode":
            return "application" if self.application_keypad else "numeric"
        elif feature_name == "input_supported":
            return True
        return None

    def handle_set_keypad_mode(self, command: "Command") -> None:
        """Handle keypad mode setting."""
        if command.args:
            mode = command.args[0]
            self.application_keypad = mode == "application"
            logger.debug(f"Keypad mode: {mode}")
        return None

    def handle_enable_mouse_tracking(self, command: "Command") -> None:
        """Handle enabling mouse tracking."""
        if command.args:
            mode = command.args[0]
            if mode == "basic":
                self.mouse_tracking = True
            elif mode == "button":
                self.mouse_button_tracking = True
            elif mode == "any":
                self.mouse_any_tracking = True
            elif mode == "sgr":
                self.mouse_sgr_mode = True
            logger.debug(f"Mouse tracking enabled: {mode}")
        return None

    def handle_disable_mouse_tracking(self, command: "Command") -> None:
        """Handle disabling mouse tracking."""
        self.mouse_tracking = False
        self.mouse_button_tracking = False
        self.mouse_any_tracking = False
        self.mouse_sgr_mode = False
        logger.debug("Mouse tracking disabled")
        return None

    def handle_input_key(self, command: "Command") -> None:
        """Handle key input."""
        if len(command.args) >= 2:
            char = command.args[0]
            modifier = int(command.args[1]) if command.args[1] else 0

            # Convert key to terminal sequence
            sequence = self._encode_key(char, modifier)
            if sequence:
                self._send_input(sequence)
        return None

    def handle_input_mouse(self, command: "Command") -> None:
        """Handle mouse input."""
        if len(command.args) >= 5:
            x = int(command.args[0])
            y = int(command.args[1])
            button = int(command.args[2])
            event_type = command.args[3]
            modifiers = set(command.args[4:]) if len(command.args) > 4 else set()

            self.mouse_x = x
            self.mouse_y = y

            # Encode mouse event if tracking is enabled
            if self.mouse_tracking or self.mouse_button_tracking or self.mouse_any_tracking:
                sequence = self._encode_mouse(x, y, button, event_type, modifiers)
                if sequence:
                    self._send_input(sequence)
        return None

    def _encode_key(self, char: str, modifier: int) -> str:
        """Encode a key press into a terminal sequence."""
        # Basic key encoding
        if len(char) == 1:
            # Regular character
            if modifier == constants.KEY_MOD_NONE:
                return char
            elif modifier & constants.KEY_MOD_CTRL:
                # Control character
                if "a" <= char.lower() <= "z":
                    return chr(ord(char.lower()) - ord("a") + 1)

        # Function keys and special keys would be handled here
        # For now, just return the character
        return char

    def _encode_mouse(self, x: int, y: int, button: int, event_type: str, modifiers: set[str]) -> str:
        """Encode a mouse event into a terminal sequence."""
        if not any([self.mouse_tracking, self.mouse_button_tracking, self.mouse_any_tracking]):
            return ""

        # Basic mouse encoding (X10 compatible)
        if event_type == "press":
            button_code = 32 + button
        elif event_type == "release":
            button_code = 32 + 3  # Release is always button 3
        else:
            return ""

        # Add modifiers
        if "shift" in modifiers:
            button_code += 4
        if "meta" in modifiers:
            button_code += 8
        if "ctrl" in modifiers:
            button_code += 16

        # Encode position (1-based, limited to 223)
        x_char = chr(min(223, x + 1 + 32))
        y_char = chr(min(223, y + 1 + 32))

        return f"\x1b[M{chr(button_code)}{x_char}{y_char}"

    def _send_input(self, data: str) -> None:
        """Send input data to the connection device."""
        if self.board:
            input_cmd = create_internal_command("SEND_INPUT", data)
            self.board.dispatch(input_cmd)


class KeyboardDevice(InputDevice):
    """Keyboard input device."""

    def __init__(self, board=None):
        super().__init__(board)
        logger.debug("KeyboardDevice initialized")


class MouseDevice(InputDevice):
    """Mouse input device."""

    def __init__(self, board=None):
        super().__init__(board)
        logger.debug("MouseDevice initialized")


class PS2KeyboardDevice(KeyboardDevice):
    """PS/2 keyboard device (classic PC keyboard)."""

    def __init__(self, board=None):
        super().__init__(board)
        logger.debug("PS2KeyboardDevice initialized")


class PS2MouseDevice(MouseDevice):
    """PS/2 mouse device (classic PC mouse)."""

    def __init__(self, board=None):
        super().__init__(board)
        logger.debug("PS2MouseDevice initialized")
