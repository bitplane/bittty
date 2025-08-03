"""Command-based parser for BitTTY terminal emulator.

This parser converts terminal byte streams into Command objects
that are dispatched to devices through the BitTTY system.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from .bittty import BitTTY

from . import constants
from .command import Command, create_c0_command, create_csi_command, create_osc_command, create_text_command

logger = logging.getLogger(__name__)


class Parser:
    """State machine parser that generates Commands for BitTTY.

    This parser processes terminal input streams and converts them
    into Command objects that are then dispatched to devices.
    Unlike the old parser that directly called terminal methods,
    this parser is decoupled from the actual terminal implementation.
    """

    def __init__(self, bittty: BitTTY) -> None:
        """Initialize the parser.

        Args:
            bittty: The BitTTY instance to dispatch commands to
        """
        self.bittty = bittty

        # Parser state
        self.current_state: str = constants.GROUND

        # Buffers for collecting sequence data
        self.intermediate_chars: list[str] = []
        self.param_buffer: str = ""
        self.parsed_params: list[int | str] = []
        self.string_buffer: str = ""
        self._string_exit_handler: Optional[Callable] = None

        logger.debug("Command parser initialized")

    def feed(self, data: str) -> None:
        """Feed data to the parser.

        Args:
            data: String data to parse
        """
        for char in data:
            self._parse_char(char)

    def _parse_char(self, char: str) -> None:
        """Parse a single character through the state machine."""
        if self.current_state == constants.GROUND:
            self._handle_ground_state(char)
        elif self.current_state == constants.ESCAPE:
            self._handle_escape_state(char)
        elif self.current_state in (constants.CSI_ENTRY, constants.CSI_PARAM, constants.CSI_INTERMEDIATE):
            self._handle_csi_state(char)
        elif self.current_state == constants.OSC_STRING:
            self._handle_osc_string_state(char)
        elif self.current_state == constants.OSC_ESC:
            self._handle_osc_esc_state(char)
        elif self.current_state == constants.DCS_STRING:
            self._handle_dcs_string_state(char)
        elif self.current_state == constants.DCS_ESC:
            self._handle_dcs_esc_state(char)
        elif self.current_state == constants.CHARSET_G0:
            self._dispatch_command(Command("SET_G0_CHARSET", "ESC", (char,), char))
            self.current_state = constants.GROUND
        elif self.current_state == constants.CHARSET_G1:
            self._dispatch_command(Command("SET_G1_CHARSET", "ESC", (char,), char))
            self.current_state = constants.GROUND
        elif self.current_state == constants.CHARSET_G2:
            self._dispatch_command(Command("SET_G2_CHARSET", "ESC", (char,), char))
            self.current_state = constants.GROUND
        elif self.current_state == constants.CHARSET_G3:
            self._dispatch_command(Command("SET_G3_CHARSET", "ESC", (char,), char))
            self.current_state = constants.GROUND

    def _handle_ground_state(self, char: str) -> None:
        """Handle characters in GROUND state."""
        if char == constants.ESC:
            self.current_state = constants.ESCAPE
            self._clear_buffers()
        elif char == constants.BEL:
            self._dispatch_command(create_c0_command("C0_BEL"))
        elif char == constants.BS:
            self._dispatch_command(create_c0_command("C0_BS"))
        elif char == constants.DEL:
            self._dispatch_command(create_c0_command("C0_DEL"))
        elif char == constants.HT:
            self._dispatch_command(create_c0_command("C0_HT"))
        elif char == constants.LF:
            self._dispatch_command(create_c0_command("C0_LF"))
        elif char == constants.CR:
            self._dispatch_command(create_c0_command("C0_CR"))
        elif char == constants.SO:
            self._dispatch_command(create_c0_command("C0_SO"))
        elif char == constants.SI:
            self._dispatch_command(create_c0_command("C0_SI"))
        elif char == constants.VT:
            self._dispatch_command(create_c0_command("C0_VT"))
        elif char == constants.FF:
            self._dispatch_command(create_c0_command("C0_FF"))
        elif ord(char) >= 0x20:  # Printable characters
            self._dispatch_command(create_text_command(char))
        else:
            # Other C0 controls
            c0_name = f"C0_{ord(char):02X}"
            self._dispatch_command(create_c0_command(c0_name))

    def _handle_escape_state(self, char: str) -> None:
        """Handle characters in ESCAPE state."""
        if char == "[":
            self.current_state = constants.CSI_ENTRY
        elif char == "]":
            self._clear_buffers()
            self.current_state = constants.OSC_STRING
        elif char == "P":
            self._clear_buffers()
            self.current_state = constants.DCS_STRING
        elif char == "\\":
            # ST - String Terminator
            self.current_state = constants.GROUND
        elif char == "=":
            self._dispatch_command(Command("SET_KEYPAD_MODE", "ESC", ("application",), char))
            self.current_state = constants.GROUND
        elif char == ">":
            self._dispatch_command(Command("SET_KEYPAD_MODE", "ESC", ("numeric",), char))
            self.current_state = constants.GROUND
        elif char == "c":
            self._dispatch_command(Command("RESET_TERMINAL", "ESC", (), char))
            self.current_state = constants.GROUND
        elif char == "D":
            self._dispatch_command(Command("INDEX", "ESC", (), char))
            self.current_state = constants.GROUND
        elif char == "M":
            self._dispatch_command(Command("REVERSE_INDEX", "ESC", (), char))
            self.current_state = constants.GROUND
        elif char == "7":
            self._dispatch_command(Command("SAVE_CURSOR", "ESC", (), char))
            self.current_state = constants.GROUND
        elif char == "8":
            self._dispatch_command(Command("RESTORE_CURSOR", "ESC", (), char))
            self.current_state = constants.GROUND
        elif char == "(":
            self.current_state = constants.CHARSET_G0
        elif char == ")":
            self.current_state = constants.CHARSET_G1
        elif char == "*":
            self.current_state = constants.CHARSET_G2
        elif char == "+":
            self.current_state = constants.CHARSET_G3
        elif char == "N":
            self._dispatch_command(Command("SINGLE_SHIFT_2", "ESC", (), char))
            self.current_state = constants.GROUND
        elif char == "O":
            self._dispatch_command(Command("SINGLE_SHIFT_3", "ESC", (), char))
            self.current_state = constants.GROUND
        else:
            logger.debug(f"Unknown escape sequence: ESC {char!r}")
            self.current_state = constants.GROUND

    def _handle_csi_state(self, char: str) -> None:
        """Handle CSI sequences."""
        if char in "0123456789":
            self.param_buffer += char
            self.current_state = constants.CSI_PARAM
        elif char == ";":
            self._parse_param()
            self.current_state = constants.CSI_PARAM
        elif char == "?" and self.current_state == constants.CSI_ENTRY:
            # DEC private mode prefix
            self.intermediate_chars.append(char)
            self.current_state = constants.CSI_PARAM
        elif char in " !\"#$%&'()*+,-./" and self.current_state != constants.CSI_INTERMEDIATE:
            self.intermediate_chars.append(char)
            self.current_state = constants.CSI_INTERMEDIATE
        elif char >= "@" and char <= "~":
            # Final byte
            self._parse_param()  # Parse any remaining parameter
            self._dispatch_csi_command(char)
            self.current_state = constants.GROUND
        else:
            logger.debug(f"Invalid CSI character: {char!r}")
            self.current_state = constants.GROUND

    def _handle_osc_string_state(self, char: str) -> None:
        """Handle OSC string state."""
        if char == constants.BEL:
            self._dispatch_osc_command(constants.BEL)
            self.current_state = constants.GROUND
        elif char == constants.ESC:
            self.current_state = constants.OSC_ESC
        else:
            self.string_buffer += char

    def _handle_osc_esc_state(self, char: str) -> None:
        """Handle OSC escape state."""
        if char == "\\":
            self._dispatch_osc_command("\x1b\\")
            self.current_state = constants.GROUND
        else:
            self.string_buffer += constants.ESC + char
            self.current_state = constants.OSC_STRING

    def _handle_dcs_string_state(self, char: str) -> None:
        """Handle DCS string state."""
        if char == constants.BEL:
            self._dispatch_dcs_command(constants.BEL)
            self.current_state = constants.GROUND
        elif char == constants.ESC:
            self.current_state = constants.DCS_ESC
        else:
            self.string_buffer += char

    def _handle_dcs_esc_state(self, char: str) -> None:
        """Handle DCS escape state."""
        if char == "\\":
            self._dispatch_dcs_command("\x1b\\")
            self.current_state = constants.GROUND
        else:
            self.string_buffer += constants.ESC + char
            self.current_state = constants.DCS_STRING

    def _dispatch_csi_command(self, final_char: str) -> None:
        """Dispatch a CSI command."""
        # Map common CSI sequences to command names
        csi_commands = {
            "A": "CSI_CUU",  # Cursor Up
            "B": "CSI_CUD",  # Cursor Down
            "C": "CSI_CUF",  # Cursor Forward
            "D": "CSI_CUB",  # Cursor Back
            "H": "CSI_CUP",  # Cursor Position
            "f": "CSI_HVP",  # Horizontal and Vertical Position
            "J": "CSI_ED",  # Erase Display
            "K": "CSI_EL",  # Erase Line
            "m": "CSI_SGR",  # Select Graphic Rendition
            "r": "CSI_DECSTBM",  # Set Top and Bottom Margins
            "h": "CSI_SM",  # Set Mode
            "l": "CSI_RM",  # Reset Mode
            "n": "CSI_DSR",  # Device Status Report
            "c": "CSI_DA",  # Device Attributes
            "P": "CSI_DCH",  # Delete Character
            "X": "CSI_ECH",  # Erase Character
            "L": "CSI_IL",  # Insert Line
            "M": "CSI_DL",  # Delete Line
            "@": "CSI_ICH",  # Insert Character
            "S": "CSI_SU",  # Scroll Up
            "T": "CSI_SD",  # Scroll Down
            "d": "CSI_VPA",  # Vertical Position Absolute
            "G": "CSI_CHA",  # Cursor Horizontal Absolute
            "s": "CSI_SCP",  # Save Cursor Position
            "u": "CSI_RCP",  # Restore Cursor Position
        }

        command_name = csi_commands.get(final_char, f"CSI_{ord(final_char):02X}")

        # Handle DEC private modes (? prefix)
        if self.intermediate_chars and self.intermediate_chars[0] == "?":
            if final_char == "h":
                command_name = "CSI_DECSET"
            elif final_char == "l":
                command_name = "CSI_DECRST"

        command = create_csi_command(command_name, tuple(self.parsed_params), final_char)
        self._dispatch_command(command)

    def _dispatch_osc_command(self, terminator: str) -> None:
        """Dispatch an OSC command."""
        # Parse OSC string: number;data
        parts = self.string_buffer.split(";", 1)
        if len(parts) >= 1:
            try:
                osc_num = int(parts[0])
                data = parts[1] if len(parts) > 1 else ""
                command = create_osc_command(f"OSC_{osc_num}", (osc_num, data), terminator)
                self._dispatch_command(command)
            except ValueError:
                logger.debug(f"Invalid OSC sequence: {self.string_buffer}")

    def _dispatch_dcs_command(self, terminator: str) -> None:
        """Dispatch a DCS command."""
        command = Command("DCS_STRING", "DCS", (self.string_buffer,), terminator)
        self._dispatch_command(command)

    def _parse_param(self) -> None:
        """Parse a parameter from the parameter buffer."""
        if self.param_buffer:
            try:
                self.parsed_params.append(int(self.param_buffer))
            except ValueError:
                self.parsed_params.append(self.param_buffer)
            self.param_buffer = ""

    def _clear_buffers(self) -> None:
        """Clear all parser buffers."""
        self.intermediate_chars.clear()
        self.param_buffer = ""
        self.parsed_params.clear()
        self.string_buffer = ""

    def _dispatch_command(self, command: Command) -> None:
        """Dispatch a command to the BitTTY instance."""
        self.bittty.dispatch(command)
        self._clear_buffers()
