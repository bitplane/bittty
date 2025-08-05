"""A state machine for processing terminal input streams."""

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

    The parser is always in one of several states (e.g. GROUND, ESCAPE, CSI_ENTRY).
    Each byte fed to the `feed()` method can cause a transition to a new
    state and/or execute a handler for a recognized escape sequence.
    """

    def __init__(self, terminal: Terminal) -> None:
        """
        Initializes the parser state.

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
        Feeds a chunk of text into the parser.

        This is the main entry point. It iterates over the data and passes each
        character to the state machine engine.
        """
        for char in data:
            self._parse_char(char)

    def _parse_char(self, char: str) -> None:
        """
        The core state machine engine.

        It looks up the current state, finds the appropriate
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
            elif char == constants.SO:
                self.terminal.shift_out()
            elif char == constants.SI:
                self.terminal.shift_in()
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
                self.terminal.numeric_keypad = False  # Application mode
                self.current_state = constants.GROUND
            elif char == ">":
                self.terminal.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, False)
                self.terminal.numeric_keypad = True  # Numeric mode
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
            elif char == "*":
                self.current_state = constants.CHARSET_G2
            elif char == "+":
                self.current_state = constants.CHARSET_G3
            elif char == "N":
                # SS2 - Single Shift 2
                self.terminal.single_shift_2()
                self.current_state = constants.GROUND
            elif char == "O":
                # SS3 - Single Shift 3
                self.terminal.single_shift_3()
                self.current_state = constants.GROUND
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
            # ESC ( <charset> - Set G0 character set
            self.terminal.set_g0_charset(char)
            self.current_state = constants.GROUND
        elif self.current_state == constants.CHARSET_G1:
            # ESC ) <charset> - Set G1 character set
            self.terminal.set_g1_charset(char)
            self.current_state = constants.GROUND
        elif self.current_state == constants.CHARSET_G2:
            # ESC * <charset> - Set G2 character set
            self.terminal.set_g2_charset(char)
            self.current_state = constants.GROUND
        elif self.current_state == constants.CHARSET_G3:
            # ESC + <charset> - Set G3 character set
            self.terminal.set_g3_charset(char)
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
                self.terminal.scroll(-1)
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
            self.terminal.scroll(count)
        elif final_char == "T":  # SD - Scroll Down
            count = self._get_param(0, 1)
            self.terminal.scroll(-count)
        elif final_char == "r":  # DECSTBM - Set Scroll Region
            top = self._get_param(0, 1) - 1  # Convert to 0-based
            bottom = self._get_param(1, self.terminal.height) - 1  # Convert to 0-based
            self.terminal.set_scroll_region(top, bottom)
        elif final_char == "b":  # REP - Repeat
            count = self._get_param(0, 1)
            self.terminal.repeat_last_character(count)
        elif final_char == "m":  # SGR - Select Graphic Rendition
            # Check for malformed sequences: ESC[>...m (device attributes syntax with SGR ending)
            if ">" in self.intermediate_chars:
                # This is a malformed sequence - device attributes should end with 'c', not 'm'
                # Likely from vim's terminal emulation leaking sequences
                logger.debug(
                    f"Ignoring malformed device attributes sequence: ESC[{';'.join(self.intermediate_chars)}{self.param_buffer}m"
                )
                return
            self._csi_dispatch_sgr()
        elif final_char == "h":  # SM - Set Mode
            self._csi_dispatch_sm_rm(True)
        elif final_char == "l":  # RM - Reset Mode
            self._csi_dispatch_sm_rm(False)
        elif final_char == "p":  # Device status queries or mode setting
            # Check for DECRQM (Request Mode) - has '$' intermediate
            if "$" in self.intermediate_chars:
                # DECRQM - Request Mode Status
                mode = self._get_param(0, 0)
                private = "?" in self.intermediate_chars

                if private:
                    # Private mode query
                    status = self._get_private_mode_status(mode)
                else:
                    # ANSI mode query
                    status = self._get_ansi_mode_status(mode)

                # Response format: ESC[?{mode};{status}$y for private modes
                # Response format: ESC[{mode};{status}$y for ANSI modes
                prefix = "?" if private else ""
                self.terminal.respond(f"\033[{prefix}{mode};{status}$y")
            else:
                # Other device queries - ignore for now
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
                self.terminal.current_buffer.set(
                    self.terminal.cursor_x, self.terminal.cursor_y, " ", self.terminal.current_ansi_code
                )
                if self.terminal.cursor_x < self.terminal.width - 1:
                    self.terminal.cursor_x += 1
        elif final_char == "n":  # Device Status Report / Cursor Position Report
            param = self._get_param(0, 0)
            if param == 6:  # CPR - Cursor Position Report
                row = self.terminal.cursor_y + 1  # Convert to 1-based
                col = self.terminal.cursor_x + 1  # Convert to 1-based
                self.terminal.respond(f"\033[{row};{col}R")
            elif param == 5:  # DSR - Device Status Report
                # Report OK status
                self.terminal.respond("\033[0n")
        elif final_char == "c":  # Device Attributes
            self._handle_device_attributes()
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
            elif param == constants.DECSCLM_SMOOTH_SCROLL:
                self.terminal.scroll_mode = set_mode
            elif param == constants.DECAWM_AUTOWRAP:
                self.terminal.auto_wrap = set_mode
            elif param == constants.DECNLM_LINEFEED_NEWLINE:
                self.terminal.linefeed_newline_mode = set_mode
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
            elif param == constants.DECBKM_BACKARROW_KEY:
                self.terminal.backarrow_key_sends_bs = set_mode
            elif param == constants.DECSCLM_SCROLLING_MODE:
                self.terminal.scroll_mode = set_mode
            elif param == constants.DECARM_AUTO_REPEAT:
                self.terminal.auto_repeat = set_mode
            elif param == constants.DECNKM_NUMERIC_KEYPAD:
                self.terminal.numeric_keypad = not set_mode  # Inverted: h = application (False), l = numeric (True)
            elif param == constants.DECCOLM_COLUMN_MODE:
                # DECCOLM: Switch between 80 and 132 columns
                if set_mode:
                    self.terminal.set_column_mode(132)
                else:
                    self.terminal.set_column_mode(80)
            elif param == constants.DECSCNM_SCREEN_MODE:
                # DECSCNM: Normal/reverse screen mode
                self.terminal.reverse_screen = set_mode
            elif param == constants.DECOM_ORIGIN_MODE:
                # DECOM: Origin mode - cursor positioning relative to scroll region
                self.terminal.origin_mode = set_mode
                # When mode changes, cursor moves to origin
                if set_mode:
                    # Origin mode: cursor to scroll region top-left
                    self.terminal.set_cursor(0, self.terminal.scroll_top)
                else:
                    # Normal mode: cursor to absolute home
                    self.terminal.set_cursor(0, 0)
            elif param == constants.DECARSM_AUTO_RESIZE:
                # DECARSM: Auto-resize mode - terminal automatically resizes
                self.terminal.auto_resize_mode = set_mode
            elif param == constants.DECKBUM_KEYBOARD_USAGE:
                # DECKBUM: Keyboard usage mode - typewriter keys send functions
                self.terminal.keyboard_usage_mode = set_mode
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
        elif cmd == constants.OSC_SET_DEFAULT_FG_COLOR:
            # OSC 10 - Set/query default foreground color
            if len(parts) >= 2 and parts[1] == "?":
                # Query mode - respond with current foreground color
                # Default to white (rgb:ffff/ffff/ffff)
                self.terminal.respond("\033]10;rgb:ffff/ffff/ffff\007")
            # TODO: Handle setting foreground color if needed
        elif cmd == constants.OSC_SET_DEFAULT_BG_COLOR:
            # OSC 11 - Set/query default background color
            if len(parts) >= 2 and parts[1] == "?":
                # Query mode - respond with current background color
                # Default to black (rgb:0000/0000/0000)
                self.terminal.respond("\033]11;rgb:0000/0000/0000\007")
            # TODO: Handle setting background color if needed
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

        # Reset character sets to defaults
        self.terminal.g0_charset = "B"  # US ASCII
        self.terminal.g1_charset = "B"
        self.terminal.g2_charset = "B"
        self.terminal.g3_charset = "B"
        self.terminal.current_charset = 0  # G0
        self.terminal.single_shift = None

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

    def _get_private_mode_status(self, mode: int) -> int:
        """Get the status of a private mode for DECRQM response.

        Returns:
        0 = not recognized
        1 = set
        2 = reset
        3 = permanently set
        4 = permanently reset
        """
        if mode == constants.DECCKM_CURSOR_KEYS_APPLICATION:
            return 1 if self.terminal.cursor_application_mode else 2
        elif mode == constants.DECSCLM_SMOOTH_SCROLL:
            return 1 if self.terminal.scroll_mode else 2
        elif mode == constants.DECAWM_AUTOWRAP:
            return 1 if self.terminal.auto_wrap else 2
        elif mode == constants.DECTCEM_SHOW_CURSOR:
            return 1 if self.terminal.cursor_visible else 2
        elif mode == constants.ALT_SCREEN_BUFFER:
            return 1 if self.terminal.in_alt_screen else 2
        elif mode == constants.ALT_SCREEN_BUFFER_OLDER:
            return 1 if self.terminal.in_alt_screen else 2
        elif mode == constants.MOUSE_TRACKING_BASIC:
            return 1 if self.terminal.mouse_tracking else 2
        elif mode == constants.MOUSE_TRACKING_BUTTON_EVENT:
            return 1 if self.terminal.mouse_button_tracking else 2
        elif mode == constants.MOUSE_TRACKING_ANY_EVENT:
            return 1 if self.terminal.mouse_any_tracking else 2
        elif mode == constants.MOUSE_SGR_MODE:
            return 1 if self.terminal.mouse_sgr_mode else 2
        elif mode == constants.MOUSE_EXTENDED_MODE:
            return 1 if self.terminal.mouse_extended_mode else 2
        elif mode == constants.DECBKM_BACKARROW_KEY:
            return 1 if self.terminal.backarrow_key_sends_bs else 2
        elif mode == constants.DECSCLM_SCROLLING_MODE:
            return 1 if self.terminal.scroll_mode else 2
        elif mode == constants.DECARM_AUTO_REPEAT:
            return 1 if self.terminal.auto_repeat else 2
        elif mode == constants.DECNKM_NUMERIC_KEYPAD:
            return 1 if not self.terminal.numeric_keypad else 2  # Inverted
        elif mode == constants.DECCOLM_COLUMN_MODE:
            return 1 if self.terminal.width == 132 else 2
        elif mode == constants.DECSCNM_SCREEN_MODE:
            return 1 if self.terminal.reverse_screen else 2
        elif mode == constants.DECOM_ORIGIN_MODE:
            return 1 if self.terminal.origin_mode else 2
        elif mode == constants.DECARSM_AUTO_RESIZE:
            return 1 if self.terminal.auto_resize_mode else 2
        elif mode == constants.DECKBUM_KEYBOARD_USAGE:
            return 1 if self.terminal.keyboard_usage_mode else 2
        else:
            return 0  # Not recognized

    def _get_ansi_mode_status(self, mode: int) -> int:
        """Get the status of an ANSI mode for DECRQM response."""
        if mode == constants.IRM_INSERT_REPLACE:
            return 1 if self.terminal.insert_mode else 2
        elif mode == constants.SRM_SEND_RECEIVE:
            return 1 if not self.terminal.local_echo else 2  # Inverted
        elif mode == constants.DECAWM_AUTOWRAP:
            return 1 if self.terminal.auto_wrap else 2
        elif mode == constants.DECTCEM_SHOW_CURSOR:
            return 1 if self.terminal.cursor_visible else 2
        else:
            return 0  # Not recognized

    def _csi_dispatch_sm_rm(self, set_mode: bool) -> None:
        """Handle SM (Set Mode) and RM (Reset Mode) sequences."""
        if "?" in self.intermediate_chars:
            self._csi_dispatch_sm_rm_private(set_mode)
            return

        for param in self.parsed_params:
            if param == constants.IRM_INSERT_REPLACE:
                self.terminal.insert_mode = set_mode
            elif param == constants.SRM_SEND_RECEIVE:
                self.terminal.local_echo = not set_mode  # Inverted: h = echo OFF, l = echo ON
            elif param == constants.DECAWM_AUTOWRAP:
                self.terminal.auto_wrap = set_mode
            elif param == constants.DECTCEM_SHOW_CURSOR:
                self.terminal.cursor_visible = set_mode

    def _handle_device_attributes(self) -> None:
        """Handle device attributes requests (DA1 and DA2)."""
        if ">" in self.intermediate_chars:
            # Secondary Device Attributes (DA2)
            # Response format: CSI > Pp ; Pv ; Pc c
            # We identify as VT420 (41), firmware version 95, with 0 for ROM cartridge
            terminal_type = constants.DA2_VT420
            firmware_version = 95
            rom_cartridge = 0
            self.terminal.respond(f"\033[>{terminal_type};{firmware_version};{rom_cartridge}c")
        else:
            # Primary Device Attributes (DA1)
            param = self._get_param(0, 0)
            if param == 0:
                # Build capabilities list based on what bittty actually supports
                capabilities = [
                    constants.DA2_VT220,  # Base terminal type
                    constants.DA1_132_COLUMNS,  # We support resizing
                    constants.DA1_SELECTIVE_ERASE,  # We have selective erase
                    constants.DA1_USER_DEFINED_KEYS,  # We support key mapping
                    constants.DA1_NATIONAL_REPLACEMENT_CHARSETS,  # We have all those charsets!
                    constants.DA1_TECH_CHARACTERS,  # We support DEC Technical charset
                    constants.DA1_USER_WINDOWS,  # We support windowing
                    constants.DA1_HORIZONTAL_SCROLLING,  # We can scroll horizontally
                    constants.DA1_ANSI_COLOR,  # We definitely support ANSI colors
                    constants.DA1_GREEK_CHARSET,  # Greek letters in DEC Technical
                ]
                # Format: CSI ? Ps ; Ps ; ... Ps c
                caps_str = ";".join(str(cap) for cap in capabilities)
                self.terminal.respond(f"\033[?{caps_str}c")
