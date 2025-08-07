"""Core Parser class with state machine and sequence dispatching.

Main parser that orchestrates all sequence handling using the specialized
dispatcher modules. Maintains state machine and provides unified feed() interface.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..terminal import Terminal

from .. import constants
from .csi import dispatch_csi
from .osc import dispatch_osc
from .dcs import dispatch_dcs
from .escape import dispatch_escape, handle_charset_escape

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
                # Handle sub-parameters: take only the main part before ':'
                main_part = part.split(":")[0]
                try:
                    params.append(int(main_part))
                except ValueError:
                    params.append(main_part)

    # Combine private markers with intermediates for backward compatibility
    all_intermediates = private_markers + intermediates

    return params, all_intermediates, final_char


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
        self.parsed_params: List[Optional[int]] = []

        # Parser state
        self.buffer = ""  # Input buffer
        self.pos = 0  # Current position in buffer
        self.mode = None  # Current paired sequence type (None when not in one)

        # Dynamic tokenizer - update based on terminal state
        self.escape_patterns = ESCAPE_PATTERNS.copy()
        self.update_tokenizer()

        # Legacy fields for backward compatibility
        self.string_buffer = ""
        self.seq_start = 0

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
        """Main sequence dispatcher - routes sequences to specialized handlers."""
        # Handle printable text
        if kind == "print":
            self.terminal.write_text(data, self.terminal.current_ansi_code)
            return

        # Singular sequences
        if kind == "bel":
            self.terminal.bell()
        elif kind == "ctrl":
            self._handle_control(data)
        elif kind == "ss3":
            self._handle_ss3(data)
        elif kind == "esc":
            self._handle_escape(data)
        elif kind == "esc_charset" or kind == "esc_charset2":
            self._handle_charset_escape(data)

        # Paired sequences
        elif kind == "csi":
            self._handle_csi(data)
        elif kind == "osc":
            self._handle_osc(data)
        elif kind == "dcs":
            self._handle_dcs(data)
        elif kind == "apc":
            self._handle_apc(data)
        elif kind == "pm":
            self._handle_pm(data)
        elif kind == "sos":
            self._handle_sos(data)
        else:
            logger.debug(f"Unknown sequence kind: {kind}")

    def _handle_control(self, data: str) -> None:
        """Handle C0/C1 control characters."""
        if data == constants.BEL:
            self.terminal.bell()
        elif data == constants.BS:
            self.terminal.backspace()
        elif data == constants.DEL:
            self.terminal.backspace()
        elif data == constants.HT:
            # Simple tab handling - move to next tab stop
            next_tab = ((self.terminal.cursor_x // 8) + 1) * 8
            self.terminal.cursor_x = min(next_tab, self.terminal.width - 1)
        elif data == constants.LF:
            self.terminal.line_feed()
        elif data == constants.VT:
            self.terminal.line_feed()  # VT treated as LF
        elif data == constants.FF:
            self.terminal.line_feed()  # FF treated as LF
        elif data == constants.CR:
            self.terminal.cursor_x = 0
        elif data == constants.SO:  # Shift Out (activate G1)
            self.terminal.current_charset = 1
        elif data == constants.SI:  # Shift In (activate G0)
            self.terminal.current_charset = 0

    def _handle_ss3(self, data: str) -> None:
        """Handle SS3 (Single Shift 3) sequences."""
        if self.terminal.application_keypad and len(data) == 3:
            # Application keypad mode - handle key codes
            key_char = data[2]
            # Convert to appropriate key event
            self.terminal.handle_application_keypad_key(key_char)
        else:
            # Charset single shift
            self.terminal.single_shift_3()

    def _handle_escape(self, data: str) -> None:
        """Handle simple escape sequences."""
        if not dispatch_escape(self.terminal, data):
            logger.debug(f"Unknown escape sequence: {data!r}")
        else:
            # Update tokenizer if keypad mode changed
            if len(data) >= 2 and data[1] in "=>":
                self.update_tokenizer()

    def _handle_charset_escape(self, data: str) -> None:
        """Handle charset designation escape sequences."""
        if not handle_charset_escape(self.terminal, data):
            logger.debug(f"Unknown charset sequence: {data!r}")

    def _handle_csi(self, data: str) -> None:
        """Handle CSI sequences using new dispatcher."""
        params, intermediates, final_char = parse_csi_sequence(data)

        # Store for legacy compatibility
        self.parsed_params = params
        self.intermediate_chars = intermediates

        # Dispatch using new O(1) lookup table
        dispatch_csi(self.terminal, final_char, params, intermediates)

    def _handle_osc(self, data: str) -> None:
        """Handle OSC sequences using new dispatcher."""
        string_content = parse_string_sequence(data, "osc")

        # Store for legacy compatibility
        self.string_buffer = string_content

        # Dispatch using new O(1) lookup table
        dispatch_osc(self.terminal, string_content)

    def _handle_dcs(self, data: str) -> None:
        """Handle DCS sequences using new dispatcher."""
        string_content = parse_string_sequence(data, "dcs")

        # Store for legacy compatibility
        self.string_buffer = string_content

        # Dispatch using new dispatcher
        dispatch_dcs(self.terminal, string_content)

    def _handle_apc(self, data: str) -> None:
        """Handle APC (Application Program Command) sequences."""
        # APC sequences are consumed but not implemented
        logger.debug(f"APC sequence received (not implemented): {data}")

    def _handle_pm(self, data: str) -> None:
        """Handle PM (Privacy Message) sequences."""
        # PM sequences are consumed but not implemented
        logger.debug(f"PM sequence received (not implemented): {data}")

    def _handle_sos(self, data: str) -> None:
        """Handle SOS (Start of String) sequences."""
        # SOS sequences are consumed but not implemented
        logger.debug(f"SOS sequence received (not implemented): {data}")

    def _get_param(self, index: int, default: int = 0) -> int:
        """
        Gets a CSI parameter at the given index, or default if missing.

        Args:
            index: Parameter index (0-based)
            default: Default value if parameter is missing or None

        Returns:
            Parameter value or default
        """
        if index < len(self.parsed_params):
            param = self.parsed_params[index]
            return param if param is not None else default
        return default

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
