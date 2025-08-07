"""A state machine for processing terminal input streams."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .terminal import Terminal

from . import constants
from .style import merge_ansi_styles

logger = logging.getLogger(__name__)


# Base escape sequence patterns
ESCAPE_PATTERNS = {
    # Paired sequence starters - these put us into "mode"
    "osc": r"\x1b\]",  # OSC start
    "dcs": r"\x1bP",  # DCS start
    "apc": r"\x1b_",  # APC start
    "pm": r"\x1b\^",  # PM start
    "sos": r"\x1bX",  # SOS start
    "csi": r"\x1b\[",  # CSI start
    # Complete sequences - these are handled immediately
    "ss3": r"\x1bO.",  # SS3 sequences (application keypad mode)
    "esc_charset": r"\x1b[()][A-Za-z0-9<>=@]",  # G0/G1 charset
    "esc_charset2": r"\x1b[*+][A-Za-z0-9<>=@]",  # G2/G3 charset
    # Terminators - these end paired sequences
    "st": r"\x1b\\",  # String Terminator (ST)
    "esc": r"\x1b[^][P_^XO\\]",  # Simple ESC sequences (catch remaining, exclude ST)
    "bel": r"\x07",  # BEL
    "csi_final": r"[\x40-\x7e]",  # CSI final byte
    # Control codes
    "ctrl": r"[\x00-\x06\x08-\x1a\x1c-\x1f\x7f]",  # C0/C1 control codes
}

# Context-specific patterns
SS3_APPLICATION = r"\x1bO."  # Application keypad mode (3 chars)
SS3_CHARSET = r"\x1bO"  # Single shift 3 for charset (2 chars)


def compile_tokenizer(patterns):
    """Compile a tokenizer regex from a dict of patterns."""
    pattern_str = "|".join(f"(?P<{k}>{v})" for k, v in patterns.items())
    return re.compile(pattern_str)


# Define which sequences are paired (have start/end) vs singular (complete)
PAIRED = {"osc", "dcs", "apc", "pm", "sos", "csi"}
SINGULAR = {"ss3", "esc", "esc_charset", "esc_charset2", "ctrl", "bel"}
STANDALONES = {"ss3", "esc", "esc_charset", "esc_charset2", "ctrl", "bel"}
SEQUENCE_STARTS = {"osc", "dcs", "apc", "pm", "sos", "csi"}

# Define valid terminators for each mode
TERMINATORS = {
    None: SEQUENCE_STARTS | STANDALONES,  # Printable mode ends at any escape
    "osc": {"st", "bel"},
    "dcs": {"st", "bel"},
    "apc": {"st"},
    "pm": {"st"},
    "sos": {"st"},
    "csi": {"csi_final"},
}

# CSI final bytes should only match in CSI mode - not in printable text
CONTEXT_SENSITIVE = {"csi_final"}


def parse_csi_sequence(data):
    """Parse complete CSI sequence and return params, intermediates, final char.

    CSI format: ESC [ [private_chars] [params] [intermediate_chars] final_char
    - private_chars: ? < = > (0x3C-0x3F)
    - params: digits and ; separators
    - intermediate_chars: space to / (0x20-0x2F)
    - final_char: @ to ~ (0x40-0x7E)

    Args:
        data: Complete CSI sequence like '\x1b[1;2H' or '\x1b[?25h'

    Returns:
        tuple: (params_list, intermediate_chars, final_char)
    """
    if len(data) < 3 or not data.startswith("\x1b["):
        return [], [], ""

    # Remove ESC[ prefix
    content = data[2:]

    # Validate that the sequence doesn't contain invalid control characters
    # (except for the final character which can be in the control range)
    for i, char in enumerate(content[:-1]):  # Check all but final char
        if ord(char) < 0x20:  # Control character
            # Invalid CSI sequence
            return [], [], ""

    # Final character is last byte
    final_char = content[-1]
    sequence = content[:-1]

    # Extract private parameter markers (? < = > at start)
    private_markers = []
    param_start = 0
    for i, char in enumerate(sequence):
        if char in "?<=>":
            private_markers.append(char)
            param_start = i + 1
        else:
            break

    # Extract intermediate characters (0x20-0x2F) at the end
    intermediates = []
    param_end = len(sequence)
    for i in range(len(sequence) - 1, -1, -1):
        char = sequence[i]
        if 0x20 <= ord(char) <= 0x2F:
            intermediates.insert(0, char)
            param_end = i
        else:
            break

    # Parse parameters (between private markers and intermediates)
    params = []
    param_part = sequence[param_start:param_end]

    if param_part:
        for part in param_part.split(";"):
            if not part:
                params.append(None)
            else:
                # Handle sub-parameters: take only main part before ':'
                main_part = part.split(":")[0]
                try:
                    params.append(int(main_part))
                except ValueError:
                    params.append(main_part)

    # Combine private markers with intermediates for backward compatibility
    all_intermediates = private_markers + intermediates

    return params, all_intermediates, final_char


def parse_string_sequence(data, sequence_type):
    """Parse complete string sequence (OSC, DCS, APC, etc.).

    Args:
        data: Complete sequence like '\x1b]0;title\x07'
        sequence_type: Type of sequence ('osc', 'dcs', etc.)

    Returns:
        str: The string content without escape codes
    """
    prefixes = {"osc": "\x1b]", "dcs": "\x1bP", "apc": "\x1b_", "pm": "\x1b^", "sos": "\x1bX"}

    prefix = prefixes.get(sequence_type, "")
    if not data.startswith(prefix):
        return ""

    # Remove prefix
    content = data[len(prefix) :]

    # Remove terminator (BEL or ST)
    if content.endswith("\x07"):  # BEL
        content = content[:-1]
    elif content.endswith("\x1b\\"):  # ST
        content = content[:-2]

    return content


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

        # Buffers for sequence data (used by CSI dispatch)
        self.intermediate_chars: List[str] = []
        self.parsed_params: List[int | str] = []

        # Parser state
        self.buffer = ""  # Input buffer
        self.pos = 0  # Current position in buffer
        self.mode = None  # Current paired sequence type (None when not in one)

        # Dynamic tokenizer - update based on terminal state
        self.escape_patterns = ESCAPE_PATTERNS.copy()
        self.update_tokenizer()

    def update_tokenizer(self):
        """Update the tokenizer regex based on current terminal state."""
        # Update SS3 pattern based on keypad mode
        if self.terminal.application_keypad:
            self.escape_patterns["ss3"] = SS3_APPLICATION  # 3-char for app keypad
        else:
            self.escape_patterns["ss3"] = SS3_CHARSET  # 2-char for charset shift

        self.tokenizer = compile_tokenizer(self.escape_patterns)

    def update_pattern(self, key: str, pattern: str):
        """Update a specific pattern in the tokenizer."""
        self.escape_patterns[key] = pattern
        self.update_tokenizer()

    def feed(self, chunk: str) -> None:
        """
        Feeds a chunk of text into the parser.

        Uses unified terminator algorithm: every mode has terminators,
        mode=None (printable) terminates on any escape sequence.
        """
        self.buffer += chunk

        for match in self.tokenizer.finditer(self.buffer, self.pos):
            kind = match.lastgroup
            start = match.start()
            end = match.end()

            # Check if this is a terminator for current mode
            if kind not in TERMINATORS[self.mode]:
                # Not a terminator for us, skip to next match
                continue

            # Found a terminator for current mode
            if self.mode is None:
                # In text mode - dispatch text before terminator
                if start > self.pos:
                    self.dispatch("print", self.buffer[self.pos : start])

                # Handle the terminator
                if kind in SEQUENCE_STARTS:
                    # Enter sequence mode, don't consume terminator yet
                    self.mode = kind
                    self.pos = start
                elif kind in STANDALONES:
                    # Dispatch standalone sequence
                    self.dispatch(kind, self.buffer[start:end])
                    self.pos = end
            else:
                # In sequence mode - dispatch complete sequence including terminator
                self.dispatch(self.mode, self.buffer[self.pos : end])
                self.mode = None
                self.pos = end

        # No more matches - handle remaining text if in text mode
        if self.mode is None and self.pos < len(self.buffer):
            end = len(self.buffer)
            # Guard against escape truncation
            if "\x1b" in self.buffer[-3:]:
                end -= 3

            if end > self.pos:
                self.dispatch("print", self.buffer[self.pos : end])
                self.pos = end

        # Clean up processed buffer
        if self.pos > 0:
            self.buffer = self.buffer[self.pos :]
            self.pos = 0

    def dispatch(self, kind, data) -> None:
        # Singular sequences
        if kind == "bel":
            self.terminal.bell()
        elif kind == "ctrl":
            if data == constants.BEL:
                self.terminal.bell()
            elif data == constants.BS:
                self.terminal.backspace()
            elif data == constants.DEL:
                self.terminal.backspace()
            elif data == constants.HT:
                # Simple tab handling - move to next tab stop
                self.terminal.cursor_x = ((self.terminal.cursor_x // 8) + 1) * 8
                if self.terminal.cursor_x >= self.terminal.width:
                    self.terminal.cursor_x = self.terminal.width - 1
            elif data == constants.LF:
                self.terminal.line_feed()
            elif data == constants.VT:
                self.terminal.line_feed()
            elif data == constants.FF:
                self.terminal.line_feed()
            elif data == constants.CR:
                self.terminal.carriage_return()
            elif data == constants.SO:
                self.terminal.shift_out()
            elif data == constants.SI:
                self.terminal.shift_in()
        elif kind == "print":
            self.terminal.write_text(data, self.terminal.current_ansi_code)
        elif kind == "ss3":
            self._handle_ss3(data)
        elif kind == "esc":
            self._handle_escape_complete(data)
        elif kind == "esc_charset":
            self._handle_charset_escape(data)
        elif kind == "esc_charset2":
            self._handle_charset_escape(data)
        elif kind == "unknown_esc":
            self._handle_unknown_escape(data)

        # Paired sequences
        elif kind == "csi":
            self._handle_csi_complete(data)
        elif kind == "osc":
            self._handle_osc_complete(data)
        elif kind == "dcs":
            self._handle_dcs_complete(data)
        elif kind == "apc":
            # APC sequences are typically ignored
            pass
        elif kind == "pm":
            # PM sequences are typically ignored
            pass

    def _handle_csi_complete(self, data):
        """Handle complete CSI sequence using regex-parsed parameters."""
        params, intermediates, final_char = parse_csi_sequence(data)

        # Skip invalid sequences (empty final_char indicates parsing failure)
        if not final_char:
            return

        # Store parsed data for existing dispatch methods
        self.parsed_params = params
        self.intermediate_chars = intermediates

        # Dispatch using existing CSI logic
        self._csi_dispatch(final_char)

    def _handle_osc_complete(self, data):
        """Handle complete OSC sequence."""
        content = parse_string_sequence(data, "osc")
        self.string_buffer = content
        self._handle_osc_dispatch()

    def _handle_dcs_complete(self, data):
        """Handle complete DCS sequence."""
        content = parse_string_sequence(data, "dcs")
        self.string_buffer = content
        self._handle_dcs_dispatch()

    def _handle_apc_complete(self, data):
        """Handle complete APC sequence."""
        # APC sequences are typically ignored by terminal emulators
        pass

    def _handle_pm_complete(self, data):
        """Handle complete PM sequence."""
        # PM sequences are typically ignored by terminal emulators
        pass

    def _handle_sos_complete(self, data):
        """Handle complete SOS sequence."""
        # SOS sequences are typically ignored by terminal emulators
        pass

    def _handle_ss3(self, data):
        """Handle SS3 sequence - keypad or charset shift based on mode."""
        if len(data) == 2:  # ESC O only - charset single shift
            # Single shift 3 for next character
            self.terminal.single_shift_3()
        elif len(data) >= 3:  # ESC O x - application keypad sequence
            seq_char = data[2]
            # Handle application keypad sequences
            if seq_char == "A":  # Cursor Up
                self.terminal.respond("\033OA")
            elif seq_char == "B":  # Cursor Down
                self.terminal.respond("\033OB")
            elif seq_char == "C":  # Cursor Right
                self.terminal.respond("\033OC")
            elif seq_char == "D":  # Cursor Left
                self.terminal.respond("\033OD")
            # Add more keypad sequences as needed
            else:
                logger.debug(f"Unknown SS3 sequence: {data!r}")

    def _handle_escape_complete(self, data):
        """Handle complete escape sequence."""
        if len(data) < 2:
            return

        seq_char = data[1]  # Character after ESC

        # Simple ESC sequences
        if seq_char == "c":  # RIS (Reset in State)
            self._reset_terminal()
        elif seq_char == "D":  # IND (Index)
            self.terminal.line_feed()
        elif seq_char == "M":  # RI (Reverse Index)
            if self.terminal.cursor_y <= self.terminal.scroll_top:
                self.terminal.scroll(-1)
            else:
                self.terminal.cursor_y -= 1
        elif seq_char == "7":  # DECSC (Save Cursor)
            self.terminal.save_cursor()
        elif seq_char == "8":  # DECRC (Restore Cursor)
            self.terminal.restore_cursor()
        elif seq_char == "=":  # DECKPAM (Application Keypad)
            self.terminal.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, True)
            self.terminal.numeric_keypad = False
            self.update_tokenizer()  # Update SS3 pattern
        elif seq_char == ">":  # DECKPNM (Numeric Keypad)
            self.terminal.set_mode(constants.DECKPAM_APPLICATION_KEYPAD, False)
            self.terminal.numeric_keypad = True
            self.update_tokenizer()  # Update SS3 pattern
        elif seq_char == "\\":  # ST (String Terminator)
            pass  # Already handled by complete sequence patterns
        elif seq_char == "N":  # SS2 (Single Shift 2)
            self.terminal.single_shift_2()
        elif seq_char == "O":  # SS3 (Single Shift 3)
            self.terminal.single_shift_3()
        else:
            logger.debug(f"Unknown escape sequence: ESC {seq_char!r}")

    def _handle_charset_escape(self, data):
        """Handle charset designation escape sequences like ESC(B."""
        if len(data) < 3:
            return

        designator = data[1]  # (, ), *, or +
        charset = data[2]  # A, B, 0, etc.

        if designator == "(":
            self.terminal.set_g0_charset(charset)
        elif designator == ")":
            self.terminal.set_g1_charset(charset)
        elif designator == "*":
            self.terminal.set_g2_charset(charset)
        elif designator == "+":
            self.terminal.set_g3_charset(charset)

    def _handle_unknown_escape(self, data):
        """Handle unknown escape sequences."""
        logger.debug(f"Unknown escape sequence: {data!r}")

    def reset(self) -> None:
        """
        Resets the parser to its initial state.
        """
        self.intermediate_chars.clear()
        self.parsed_params.clear()
        self.string_buffer = ""
        self.buffer = ""
        self.pos = 0
        self.mode = None
        self.seq_start = 0

    # Legacy methods for test compatibility - will be removed once tests are updated
    def _clear(self) -> None:
        """Clears temporary buffers (legacy method for tests)."""
        self.intermediate_chars.clear()
        self.parsed_params.clear()
        self.string_buffer = ""

    def _split_params(self, param_string: str) -> None:
        """Parse parameter string (legacy method for tests)."""
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

    def _reset_terminal(self) -> None:
        """Reset terminal to initial state."""
        self.terminal.clear_screen(constants.ERASE_ALL)
        self.terminal.set_cursor(0, 0)
        self.terminal.current_ansi_code = ""

    def _get_param(self, index: int, default: int) -> int:
        """
        Gets a numeric parameter from the parsed list, with a default value.
        """
        if index < len(self.parsed_params):
            param = self.parsed_params[index]
            return param if param is not None else default
        return default

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
        # Parameters are already parsed by _handle_csi_complete and stored in self.parsed_params

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
                params_str = ";".join(str(p) for p in self.parsed_params)
                logger.debug(
                    f"Ignoring malformed device attributes sequence: ESC[{';'.join(self.intermediate_chars)}{params_str}m"
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
            params_str = ";".join(str(p) for p in self.parsed_params) if self.parsed_params else "<no params>"
            intermediates_str = "".join(self.intermediate_chars)
            logger.debug(f"Unknown CSI sequence: ESC[{intermediates_str}{params_str}{final_char}")

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
