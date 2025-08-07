"""Core Parser class with state machine and sequence dispatching.

Main parser that orchestrates all sequence handling using the specialized
dispatcher modules. Maintains state machine and provides unified feed() interface.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import TYPE_CHECKING

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


@lru_cache(maxsize=300)
def parse_string_sequence(data, sequence_type):
    """BLAZING FAST string sequence parser with LRU caching! 🚀

    Optimizations:
    1. **LRU caching**: Smart eviction keeps most recent sequences
    2. **Fast paths**: Handle common OSC/DCS patterns with minimal processing
    3. **Reduced lookups**: Direct character checking instead of dictionary lookup
    4. **Efficient slicing**: Minimize string operations

    Args:
        data: Complete sequence like '\x1b]0;title\x07'
        sequence_type: Type of sequence ('osc', 'dcs', etc.)

    Returns:
        str: The string content without escape codes
    """

    # ⚡ FAST PATH: Direct character checking instead of dict lookup
    if sequence_type == "osc":
        if len(data) < 3 or data[0] != "\x1b" or data[1] != "]":
            return ""
        prefix_len = 2
    elif sequence_type == "dcs":
        if len(data) < 3 or data[0] != "\x1b" or data[1] != "P":
            return ""
        prefix_len = 2
    elif sequence_type == "apc":
        if len(data) < 3 or data[0] != "\x1b" or data[1] != "_":
            return ""
        prefix_len = 2
    elif sequence_type == "pm":
        if len(data) < 3 or data[0] != "\x1b" or data[1] != "^":
            return ""
        prefix_len = 2
    elif sequence_type == "sos":
        if len(data) < 3 or data[0] != "\x1b" or data[1] != "X":
            return ""
        prefix_len = 2
    else:
        # Unknown sequence type - fallback
        return ""

    # Remove prefix efficiently
    content = data[prefix_len:]

    # ⚡ FAST PATH: Check terminator by looking at end characters directly
    content_len = len(content)
    if content_len == 0:
        result = ""
    elif content_len >= 2 and content[-2:] == "\x1b\\":  # ST terminator
        result = content[:-2]
    elif content[-1] == "\x07":  # BEL terminator
        result = content[:-1]
    else:
        # No terminator found - return content as-is
        result = content

    return result


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
        """Handle CSI sequences using revolutionary new dispatcher! 🚀"""
        # Pass raw data directly - no redundant parsing!
        dispatch_csi(self.terminal, data)

    def _handle_osc(self, data: str) -> None:
        """Handle OSC sequences using new dispatcher."""
        string_content = parse_string_sequence(data, "osc")

        # Dispatch using new O(1) lookup table
        dispatch_osc(self.terminal, string_content)

    def _handle_dcs(self, data: str) -> None:
        """Handle DCS sequences using new dispatcher."""
        string_content = parse_string_sequence(data, "dcs")

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

    def reset(self) -> None:
        """
        Resets the parser to its initial state.
        """
        self.buffer = ""
        self.pos = 0
        self.mode = None
