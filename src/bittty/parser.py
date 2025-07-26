"""
The Terminal Parser: A state machine for processing terminal input streams.

This module provides the `Parser` class, which consumes a stream of bytes
from a pseudo-terminal (pty) and translates it into high-level calls to a
`ScreenWriter` API.

It is a direct architectural port of tmux's `input.c`, implementing the same
finite state machine described by Paul Williams (https://vt100.net/emu/).

The core logic is in the `feed()` method, which processes each byte, moves
between states, and calls the appropriate handler methods for escape sequences.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, List, Optional

if TYPE_CHECKING:
    from .terminal import Terminal

from . import constants
from .style import merge_ansi_styles

logger = logging.getLogger(__name__)


class Parser:
    """
    A state machine that parses a stream of terminal control codes.

    The parser is always in one of several states (GROUND, ESCAPE, CSI_ENTRY,
    etc.). Each byte fed to the `feed()` method can cause a transition to a new
    state and/or execute a handler for a recognized escape sequence.
    """

    def __init__(self, terminal: Terminal) -> None:
        """
        Initializes the parser state. Replaces `input_init()`.

        Args:
            terminal: A Terminal object that the parser will manipulate.
        """
        self.terminal = terminal

        # The current state of the parser (e.g., 'GROUND', 'ESCAPE').
        self.current_state: str = constants.GROUND

        # --- Buffers for collecting sequence data ---
        self.intermediate_chars: List[str] = []
        self.param_buffer: str = ""
        self.parsed_params: List[int | str] = []
        self.string_buffer: str = ""  # For OSC, DCS, APC strings
        self._string_exit_handler: Optional[Callable] = None

        # --- Current Cell Attributes ---
        # ANSI sequence is stored in terminal.current_ansi_code

    def feed(self, data: str) -> None:
        """
        Feeds a chunk of text into the parser. Replaces `input_parse_buffer()`.

        This is the main entry point. It iterates over the data and passes each
        character to the state machine engine.
        """
        for char in data:
            self._parse_char(char)

    def _parse_char(self, char: str) -> None:
        """
        The core state machine engine.

        It looks up the current state in `self.states`, finds the appropriate
        transition for the given byte, executes the handler, and moves to the
        next state.
        """
        # Simplified parser - handle basic cases
        if self.current_state == constants.GROUND:
            if char == constants.ESC:
                self.current_state = constants.ESCAPE
                self._clear()
            elif char == constants.BEL:
                self.terminal.bell()
            elif char == constants.BS:
                self.terminal.backspace()
            elif char == constants.DEL:
                self.terminal.backspace()
            elif char == constants.HT:
                # Simple tab handling - move to next tab stop
                self.terminal.cursor_x = ((self.terminal.cursor_x // 8) + 1) * 8
                if self.terminal.cursor_x >= self.terminal.width:
                    self.terminal.cursor_x = self.terminal.width - 1
            elif char == constants.LF:
                self.terminal.line_feed()
            elif char == constants.CR:
                self.terminal.carriage_return()
            elif ord(char) >= 0x20:  # Printable characters
                # Use current ANSI sequence
                self.terminal.write_text(char, self.terminal.current_ansi_code)
        elif self.current_state == constants.ESCAPE:
            if char == "[":
                self.current_state = constants.CSI_ENTRY
            elif char == "]":
                self._clear()
                self.current_state = constants.OSC_STRING
            elif char == "=":
                self.terminal.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, True)
                self.current_state = constants.GROUND
            elif char == ">":
                self.terminal.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, False)
                self.current_state = constants.GROUND
            elif char == "P":
                self._clear()
                self.current_state = constants.DCS_STRING
            elif char == "\\":
                self.current_state = constants.GROUND
            elif char == "c":
                self._esc_dispatch(char)
                self.current_state = constants.GROUND
            elif char == "D":
                self._esc_dispatch(char)
                self.current_state = constants.GROUND
            elif char == "M":
                self._esc_dispatch(char)
                self.current_state = constants.GROUND
            elif char == "7":
                self._esc_dispatch(char)
                self.current_state = constants.GROUND
            elif char == "8":
                self._esc_dispatch(char)
                self.current_state = constants.GROUND
            elif char == ">":
                self.current_state = constants.GROUND
            elif char == "(":
                self.current_state = constants.CHARSET_G0
            elif char == ")":
                self.current_state = constants.CHARSET_G1
            else:
                logger.debug(f"Unknown escape sequence: ESC {char!r}")
                self.current_state = constants.GROUND
        elif self.current_state in (constants.CSI_ENTRY, constants.CSI_PARAM, constants.CSI_INTERMEDIATE):
            self._handle_csi(char)
        elif self.current_state == constants.OSC_STRING:
            if char == constants.BEL:
                self._handle_osc_dispatch()
                self.current_state = constants.GROUND
            elif char == constants.ESC:
                self.current_state = constants.OSC_ESC
            else:
                self.string_buffer += char
        elif self.current_state == constants.OSC_ESC:
            if char == "\\":
                self._handle_osc_dispatch()
                self.current_state = constants.GROUND
            else:
                self.string_buffer += constants.ESC + char
                self.current_state = constants.OSC_STRING
        elif self.current_state == constants.DCS_STRING:
            if char == constants.BEL:
                self._handle_dcs_dispatch()
                self.current_state = constants.GROUND
            elif char == constants.ESC:
                self.current_state = constants.DCS_ESC
            else:
                self.string_buffer += char
        elif self.current_state == constants.DCS_ESC:
            if char == "\\":
                self._handle_dcs_dispatch()
                self.current_state = constants.GROUND
            else:
                self.string_buffer += constants.ESC + char
                self.current_state = constants.DCS_STRING
        elif self.current_state == constants.CHARSET_G0:
            self.current_state = constants.GROUND
        elif self.current_state == constants.CHARSET_G1:
            self.current_state = constants.GROUND

    def _handle_csi(self, char: str) -> None:
        """Generic handler for CSI_ENTRY, CSI_PARAM, and CSI_INTERMEDIATE states."""
        # Final byte is the same for all CSI states
        if "\x40" <= char <= "\x7e":
            self._csi_dispatch(char)
            self.current_state = constants.GROUND
            return

        # Parameter bytes
        if "\x30" <= char <= "\x3b":
            self._collect_parameter(char)
            if self.current_state == constants.CSI_ENTRY:
                self.current_state = constants.CSI_PARAM
            return

        # Intermediate bytes
        if "\x20" <= char <= "\x2f":
            self._collect_intermediate(char)
            self.current_state = constants.CSI_INTERMEDIATE
            return

        # Private parameter bytes (only valid in CSI_ENTRY)
        if "\x3c" <= char <= "\x3f":
            if self.current_state == constants.CSI_ENTRY:
                self._collect_intermediate(char)
                self.current_state = constants.CSI_PARAM
            else:
                logger.debug(f"Invalid CSI character: {char!r}")
                self.current_state = constants.GROUND
            return

        logger.debug(f"Invalid CSI character: {char!r}")
        self.current_state = constants.GROUND

    def reset(self) -> None:
        """
        Resets the parser to its initial ground state.
        """
        self._clear()
        self.current_state = constants.GROUND

    # --- State Buffer and Parameter Handling Methods ---

    def _clear(self) -> None:
        """
        Clears all temporary buffers used for parsing sequences.

        This is called when entering a new escape sequence (ESC, CSI, OSC, etc.)
        to ensure old parameter or intermediate data is discarded.
        """
        self.intermediate_chars.clear()
        self.param_buffer = ""
        self.parsed_params.clear()
        self.string_buffer = ""

    def _collect_intermediate(self, char: str) -> None:
        """
        Collects an intermediate character for an escape sequence.

        In a sequence like `CSI ? 25 h`, the '?' is an intermediate character.
        This method appends it to an internal buffer.
        """
        self.intermediate_chars.append(char)

    def _collect_parameter(self, char: str) -> None:
        """
        Collects a parameter character for a sequence.

        This collects characters like '3', '8', ';', '5' from a parameter
        string like "38;5;21". The `_split_params` method will later parse this.
        """
        self.param_buffer += char

    def _split_params(self, param_string: str) -> None:
        """
        Parses parameter string like "1;2;3" or "38;5;196" into integers.

        Handles empty parameters and sub-parameters (takes only the first part before ':').
        """
        self.parsed_params.clear()
        if not param_string:
            return

        for part in param_string.split(";"):
            if not part:
                self.parsed_params.append(None)
                continue

            # Handle sub-parameters: take only the main part before ':'
            main_part = part.split(":")[0]

            try:
                self.parsed_params.append(int(main_part))
            except ValueError:
                self.parsed_params.append(0)

    def _get_param(self, index: int, default: int) -> int:
        """
        Gets a numeric parameter from the parsed list, with a default value.
        """
        if index < len(self.parsed_params):
            param = self.parsed_params[index]
            return param if param is not None else default
        return default

    # --- Escape (ESC) Sequence Dispatchers ---

    def _esc_dispatch(self, final_char: str) -> None:
        """
        Handles an ESC-based escape sequence (ones that do not start with CSI).

        This is a top-level dispatcher that will look up the sequence in a
        dispatch table and call the appropriate handler method.

        Relevant constants (`enum input_esc_type`):
        - `DECSC`: Save cursor position and attributes.
        - `DECRC`: Restore saved cursor position and attributes.
        - `DECKPAM`: Enter keypad application mode.
        - `DECKPNM`: Exit keypad numeric mode.
        - `RIS`: Hard reset to initial state.
        - `IND`: Index (move cursor down one line).
        - `NEL`: Next Line (equivalent to CR+LF).
        - `HTS`: Set a horizontal tab stop at the current cursor column.
        - `RI`: Reverse Index (move cursor up one line, scrolling if needed).
        - `SCSG0_ON`, `SCSG1_ON`: Designate G0/G1 charsets as ACS line drawing.
        - `SCSG0_OFF`, `SCSG1_OFF`: Designate G0/G1 charsets as ASCII.
        - `DECALN`: Screen alignment test (fills screen with 'E').
        """
        if final_char == "c":  # RIS (Reset in State)
            self._reset_terminal()
        elif final_char == "D":  # IND (Index)
            self.terminal.line_feed()
        elif final_char == "M":  # RI (Reverse Index)
            if self.terminal.cursor_y <= self.terminal.scroll_top:
                self.terminal.scroll_down(1)
            else:
                self.terminal.cursor_y -= 1
        elif final_char == "7":  # DECSC (Save Cursor)
            self.terminal.save_cursor()
        elif final_char == "8":  # DECRC (Restore Cursor)
            self.terminal.restore_cursor()
        # Add more ESC sequences as needed

    # --- Control Sequence Introducer (CSI) Dispatchers ---

    def _csi_dispatch(self, final_char: str) -> None:
        """
        Handles a CSI-based escape sequence (starts with `ESC[`).

        This is a major dispatcher that handles dozens of terminal commands. It will
        look up the final character and intermediate characters in a dispatch
        table and call the specific handler.

        Key branches from C (`enum input_csi_type`):
        - `CUP` (Cursor Position): Moves cursor to (y, x).
        - `ED` (Erase in Display): Clears parts of the screen.
        - `EL` (Erase in Line): Clears parts of the current line.
        - `SGR` (Select Graphic Rendition): Calls `_csi_dispatch_sgr` to set colors/attrs.
        - `SM`/`RM` (Set/Reset Mode): Calls helpers to set/reset terminal modes.
        - `DECSTBM`: Sets the top and bottom margins for the scroll region.
        - `ICH`/`DCH`: Insert/Delete characters.
        - `IL`/`DL`: Insert/Delete lines.
        - `SU`/`SD`: Scroll Up/Down.
        - `DA`/`XDA`: Device Attributes request, which requires sending a response.
        - `DSR`: Device Status Report request, also requires a response.
        - `REP`: Repeat the preceding character N times.
        - `DECSCUSR`: Set cursor style (block, underline, bar).
        """
        # Parse parameters
        self._split_params(self.param_buffer)

        # Handle common CSI sequences
        if final_char == "H" or final_char == "f":  # CUP - Cursor Position
            row = self._get_param(0, 1) - 1  # Convert to 0-based
            col = self._get_param(1, 1) - 1  # Convert to 0-based
            self.terminal.set_cursor(col, row)
        elif final_char == "A":  # CUU - Cursor Up
            count = self._get_param(0, 1)
            self.terminal.cursor_y = max(0, self.terminal.cursor_y - count)
        elif final_char == "B":  # CUD - Cursor Down
            count = self._get_param(0, 1)
            self.terminal.cursor_y = min(self.terminal.height - 1, self.terminal.cursor_y + count)
        elif final_char == "C":  # CUF - Cursor Forward
            count = self._get_param(0, 1)
            self.terminal.cursor_x = min(self.terminal.width - 1, self.terminal.cursor_x + count)
        elif final_char == "D":  # CUB - Cursor Backward
            count = self._get_param(0, 1)
            self.terminal.cursor_x = max(0, self.terminal.cursor_x - count)
        elif final_char == "G":  # CHA - Cursor Horizontal Absolute
            col = self._get_param(0, 1) - 1  # Convert to 0-based
            self.terminal.set_cursor(col, None)
        elif final_char == "d":  # VPA - Vertical Position Absolute
            row = self._get_param(0, 1) - 1  # Convert to 0-based
            self.terminal.set_cursor(None, row)
        elif final_char == "J":  # ED - Erase in Display
            mode = self._get_param(0, 0)
            self.terminal.clear_screen(mode)
        elif final_char == "K":  # EL - Erase in Line
            mode = self._get_param(0, 0)
            self.terminal.clear_line(mode)
        elif final_char == "L":  # IL - Insert Lines
            count = self._get_param(0, 1)
            self.terminal.insert_lines(count)
        elif final_char == "M":  # DL - Delete Lines
            count = self._get_param(0, 1)
            self.terminal.delete_lines(count)
        elif final_char == "@":  # ICH - Insert Characters
            count = self._get_param(0, 1)
            # Use current ANSI sequence for inserted spaces
            self.terminal.insert_characters(count, self.terminal.current_ansi_code)
        elif final_char == "P":  # DCH - Delete Characters
            count = self._get_param(0, 1)
            self.terminal.delete_characters(count)
        elif final_char == "S":  # SU - Scroll Up
            count = self._get_param(0, 1)
            self.terminal.scroll_up(count)
        elif final_char == "T":  # SD - Scroll Down
            count = self._get_param(0, 1)
            self.terminal.scroll_down(count)
        elif final_char == "r":  # DECSTBM - Set Scroll Region
            top = self._get_param(0, 1) - 1  # Convert to 0-based
            bottom = self._get_param(1, self.terminal.height) - 1  # Convert to 0-based
            self.terminal.set_scroll_region(top, bottom)
        elif final_char == "b":  # REP - Repeat
            count = self._get_param(0, 1)
            self.terminal.repeat_last_character(count)
        elif final_char == "m":  # SGR - Select Graphic Rendition
            self._csi_dispatch_sgr()
        elif final_char == "h":  # SM - Set Mode
            self._csi_dispatch_sm_rm(True)
        elif final_char == "l":  # RM - Reset Mode
            self._csi_dispatch_sm_rm(False)
        elif final_char == "p":  # Device status queries or mode setting
            # Various device status queries - we consume but don't respond
            # This could be device attributes, mode queries, etc.
            pass
        elif final_char == "t":  # Window operations
            # Various window operations (resize, position queries, etc.)
            # We consume but don't implement window operations
            pass
        elif final_char == "^":  # PM (Privacy Message)
            # Privacy message - we consume but don't implement
            pass
        elif final_char == "s":  # DECSC - Save Cursor (alternative)
            # Save cursor position and attributes
            self.terminal.save_cursor()
        elif final_char == "u":  # DECRC - Restore Cursor (alternative)
            # Restore cursor position and attributes
            self.terminal.restore_cursor()
        elif final_char == "X":  # ECH - Erase Character (possibly with intermediate)
            # Erase n characters at cursor position
            count = self._get_param(0, 1)
            # For now, treat this as delete characters (could be improved)
            for _ in range(count):
                self.terminal.current_buffer.set(self.terminal.cursor_x, self.terminal.cursor_y, " ")
                if self.terminal.cursor_x < self.terminal.width - 1:
                    self.terminal.cursor_x += 1
        elif final_char == "n":  # Device Status Report / Cursor Position Report
            # This is often used by programs to query cursor position
            # We don't need to respond as this is just for compatibility
            pass
        elif final_char == "c":  # Device Attributes
            # Programs query terminal capabilities - we just ignore
            pass
        else:
            # Unknown CSI sequence, log it
            params_str = self.param_buffer if self.param_buffer else "<no params>"
            logger.debug(f"Unknown CSI sequence: ESC[{params_str}{final_char}")

    def _csi_dispatch_sm_rm_private(self, set_mode: bool) -> None:
        """
        Handles private SM/RM sequences (prefixed with `?`).

        Key modes handled (`MODE_*` constants):
        - `?1` (DECCKM): Set cursor keys to application mode.
        - `?7` (DECAWM): Enable/disable autowrap mode.
        - `?12`: Set cursor blinking.
        - `?25`: Show/hide cursor.
        - `?1000-?1003, ?1005, ?1006`: Enable various mouse tracking modes.
        - `?1049`: Enable alternate screen buffer.
        - `?2004`: Enable bracketed paste mode.
        """
        for param in self.parsed_params:
            if param == constants.DECCKM_CURSOR_KEYS_APPLICATION:
                self.terminal.cursor_application_mode = set_mode
            elif param == constants.DECAWM_AUTOWRAP:
                self.terminal.auto_wrap = set_mode
            elif param == constants.DECTCEM_SHOW_CURSOR:
                self.terminal.cursor_visible = set_mode
            elif param == constants.ALT_SCREEN_BUFFER_OLDER:
                if set_mode:
                    self.terminal.alternate_screen_on()
                else:
                    self.terminal.alternate_screen_off()
            elif param == constants.ALT_SCREEN_BUFFER:
                if set_mode:
                    self.terminal.alternate_screen_on()
                else:
                    self.terminal.alternate_screen_off()
            elif param == constants.MOUSE_TRACKING_BASIC:
                self.terminal.set_mode(constants.MOUSE_TRACKING_BASIC, set_mode, private=True)
            elif param == constants.MOUSE_TRACKING_BUTTON_EVENT:
                self.terminal.set_mode(constants.MOUSE_TRACKING_BUTTON_EVENT, set_mode, private=True)
            elif param == constants.MOUSE_TRACKING_ANY_EVENT:
                self.terminal.set_mode(constants.MOUSE_TRACKING_ANY_EVENT, set_mode, private=True)
            elif param == constants.MOUSE_SGR_MODE:
                self.terminal.set_mode(constants.MOUSE_SGR_MODE, set_mode, private=True)
            elif param == constants.MOUSE_EXTENDED_MODE:
                self.terminal.set_mode(constants.MOUSE_EXTENDED_MODE, set_mode, private=True)
            # Add more private modes as needed

    # --- OSC, DCS, and other String-based Sequence Handlers ---

    def _handle_osc_dispatch(self) -> None:
        """
        Dispatches an OSC (Operating System Command) string.

        Parses the command number and calls the appropriate handler.
        - `0` or `2`: Set window/icon title.
        - `4`: Set color palette entry.
        - `7`: Set current working directory/URL.
        - `8`: Define hyperlink.
        - `10`: Set default foreground color.
        - `11`: Set default background color.
        - `12`: Set cursor color.
        - `52`: Set/query clipboard content.
        - `104`: Reset color palette entry.
        - `110, 111, 112`: Reset fg/bg/cursor color to default.
        """
        if not self.string_buffer:
            return

        # Parse OSC command: number;data
        parts = self.string_buffer.split(";", 1)
        if len(parts) < 1:
            return

        try:
            cmd = int(parts[0])
        except ValueError:
            return

        if cmd == constants.OSC_SET_TITLE_AND_ICON:
            # OSC 0 - Set both title and icon title
            if len(parts) >= 2:
                title_text = parts[1]
                self.terminal.set_title(title_text)
                self.terminal.set_icon_title(title_text)
        elif cmd == constants.OSC_SET_ICON_TITLE:
            # OSC 1 - Set icon title only
            if len(parts) >= 2:
                icon_title_text = parts[1]
                self.terminal.set_icon_title(icon_title_text)
        elif cmd == constants.OSC_SET_TITLE:
            # OSC 2 - Set title only
            if len(parts) >= 2:
                title_text = parts[1]
                self.terminal.set_title(title_text)
        else:
            # For other OSC sequences, we just consume them without implementing them
            # This prevents them from leaking through to the terminal output
            pass

    def _handle_dcs_dispatch(self) -> None:
        """
        Dispatches a DCS (Device Control String).

        Primarily used for passthrough (`tmux;...`) sequences or for things
        like Sixel graphics if support is enabled.
        """
        pass

    def _reset_terminal(self) -> None:
        """Reset terminal to initial state."""
        self.terminal.clear_screen(constants.ERASE_ALL)
        self.terminal.set_cursor(0, 0)
        self.terminal.current_ansi_code = ""

    def _csi_dispatch_sgr(self) -> None:
        """
        Handles SGR (Select Graphic Rendition) sequences to set text style.
        Merges new style with existing style.
        """
        if not self.parsed_params:
            self.parsed_params = [0]  # Default to reset

        # Build the ANSI sequence from the original parameters
        params_str = ";".join(str(p) if p is not None else "" for p in self.parsed_params)
        new_ansi_sequence = f"\033[{params_str}m"

        # Merge with existing style
        self.terminal.current_ansi_code = merge_ansi_styles(self.terminal.current_ansi_code, new_ansi_sequence)

    def _csi_dispatch_sm_rm(self, set_mode: bool) -> None:
        """Handle SM (Set Mode) and RM (Reset Mode) sequences."""
        if "?" in self.intermediate_chars:
            self._csi_dispatch_sm_rm_private(set_mode)
            return

        for param in self.parsed_params:
            if param == constants.DECAWM_AUTOWRAP:
                self.terminal.auto_wrap = set_mode
            elif param == constants.DECTCEM_SHOW_CURSOR:
                self.terminal.cursor_visible = set_mode
