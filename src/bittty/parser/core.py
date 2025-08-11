"""Core Parser class with state machine and sequence dispatching."""

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

# keep DCS/ESC handlers as before
from .dcs import dispatch_dcs
from .escape import dispatch_escape, handle_charset_escape

logger = logging.getLogger(__name__)

# Unified 7-bit + 8-bit tokens (single named groups → no aliasing)
ESCAPE_PATTERNS = {
    # Paired sequence starters
    "osc": r"(?:\x1b\]|\x9D)",
    "dcs": r"(?:\x1bP|\x90)",
    "apc": r"(?:\x1b_|\x9F)",
    "pm": r"(?:\x1b\^|\x9E)",
    "sos": r"(?:\x1bX|\x98)",
    "csi": r"(?:\x1b\[|\x9B)",
    # Terminators / cancel
    "st": r"(?:\x1b\\|\x9C)",  # String Terminator
    "bel": r"\x07",
    "cancel": r"[\x18\x1A]",  # CAN / SUB abort current sequence
    # Singles / minis
    "ss2": r"(?:\x1bN|\x8E)",
    "ss3": r"(?:\x1bO|\x8F)",
    # Simple ESC minis (not starters for paired strings)
    "esc": r"\x1b[^][P_^XO\\]",  # excludes [,],P,_,^,X,ST
    "esc_charset": r"\x1b[()][A-Za-z0-9<>=@]",  # G0/G1
    "esc_charset2": r"\x1b[*+][A-Za-z0-9<>=@]",  # G2/G3
    # CSI final (only relevant in CSI mode)
    "csi_final": r"[\x40-\x7E]",
    # C0/C1 single-byte controls (excluding BEL/CAN/SUB here)
    "ctrl": r"[\x00-\x06\x08-\x17\x19\x1B-\x1F\x7F]",
    # End-of-buffer guard: incomplete starter at buffer end (no ST here)
    "trail": r"(?:\x1b[\[\]P_^X]|\x90|\x9B|\x9D|\x9E|\x9F|\x98)\Z",
}

PAIRED = {"osc", "dcs", "apc", "pm", "sos", "csi"}
STANDALONES = {"ss2", "ss3", "esc", "esc_charset", "esc_charset2", "ctrl", "bel"}
SEQUENCE_STARTS = {"osc", "dcs", "apc", "pm", "sos", "csi"}

TERMINATORS = {
    None: SEQUENCE_STARTS | STANDALONES | {"cancel"},  # in GROUND, these trigger handling
    "osc": {"st", "bel", "cancel"},
    "dcs": {"st", "bel", "cancel"},
    "apc": {"st", "cancel"},
    "pm": {"st", "cancel"},
    "sos": {"st", "cancel"},
    "csi": {"csi_final", "cancel"},
}


@lru_cache(maxsize=300)
def parse_string_sequence(data: str, sequence_type: str) -> str:
    """Return string content without prefix/terminator (OSC/DCS/APC/PM/SOS)."""
    if not data:
        return ""
    # Remove prefix (supports 7-bit ESC-prefixed and 8-bit C1)
    if sequence_type == "osc":
        if data[0] == "\x9d":
            content = data[1:]
        elif data.startswith("\x1b]"):
            content = data[2:]
        else:
            return ""
    elif sequence_type == "dcs":
        if data[0] == "\x90":
            content = data[1:]
        elif data.startswith("\x1bP"):
            content = data[2:]
        else:
            return ""
    elif sequence_type == "apc":
        if data[0] == "\x9f":
            content = data[1:]
        elif data.startswith("\x1b_"):
            content = data[2:]
        else:
            return ""
    elif sequence_type == "pm":
        if data[0] == "\x9e":
            content = data[1:]
        elif data.startswith("\x1b^"):
            content = data[2:]
        else:
            return ""
    elif sequence_type == "sos":
        if data[0] == "\x98":
            content = data[1:]
        elif data.startswith("\x1bX"):
            content = data[2:]
        else:
            return ""
    else:
        return ""

    # Strip terminator: ST (ESC \ or 0x9C) or BEL (OSC only)
    if content.endswith("\x1b\\"):
        return content[:-2]
    if content.endswith("\x9c"):
        return content[:-1]
    if sequence_type == "osc" and content.endswith("\x07"):
        return content[:-1]
    return content


def compile_tokenizer(patterns: dict[str, str]) -> re.Pattern:
    return re.compile("|".join(f"(?P<{k}>{v})" for k, v in patterns.items()))


class Parser:
    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal
        self.buffer = ""
        self.pos = 0
        self.mode: str | None = None
        self.escape_patterns = ESCAPE_PATTERNS.copy()
        self.tokenizer = compile_tokenizer(self.escape_patterns)

    def update_tokenizer(self) -> None:
        # kept for API compatibility; tokenizer is static in this design
        self.tokenizer = compile_tokenizer(self.escape_patterns)

    def update_pattern(self, key: str, pattern: str) -> None:
        self.escape_patterns[key] = pattern
        self.update_tokenizer()

    def feed(self, chunk: str) -> None:
        self.buffer += chunk
        trail_start: int | None = None

        for match in self.tokenizer.finditer(self.buffer, self.pos):
            kind = match.lastgroup
            start, end = match.start(), match.end()

            if kind == "trail":
                trail_start = start
                break

            if kind not in TERMINATORS[self.mode]:
                continue

            if self.mode is None:
                # flush preceding printables
                if start > self.pos:
                    self.dispatch("print", self.buffer[self.pos : start])

                if kind in SEQUENCE_STARTS:
                    # enter paired sequence; don't consume starter
                    self.mode = kind
                    self.pos = start
                elif kind == "cancel":
                    # CAN/SUB in ground: ignore
                    self.pos = end
                elif kind in STANDALONES:
                    self.dispatch(kind, self.buffer[start:end])
                    self.pos = end
            else:
                # inside a paired sequence
                if kind == "cancel":
                    # abort sequence: drop buffered content
                    self.mode = None
                    self.pos = end
                elif self.mode == "csi" and kind == "csi_final":
                    self.dispatch("csi", self.buffer[self.pos : end])
                    self.mode = None
                    self.pos = end
                else:
                    # strings (OSC/DCS/APC/PM/SOS) terminated by ST/BEL
                    self.dispatch(self.mode, self.buffer[self.pos : end])
                    self.mode = None
                    self.pos = end

        # After scanning, handle trailing starter guard
        if trail_start is not None:
            if self.mode is None and trail_start > self.pos:
                self.dispatch("print", self.buffer[self.pos : trail_start])
                self.pos = trail_start
        else:
            # no trailing starter; flush remaining printables in ground
            if self.mode is None and self.pos < len(self.buffer):
                self.dispatch("print", self.buffer[self.pos :])
                self.pos = len(self.buffer)

        # compact buffer
        if self.pos > 0:
            self.buffer = self.buffer[self.pos :]
            self.pos = 0

    def dispatch(self, kind: str, data: str) -> None:
        if kind == "print":
            self.terminal.write_text(data, self.terminal.current_ansi_code)
            return

        # Standalones
        if kind == "bel":
            self.terminal.bell()
            return
        if kind == "ctrl":
            self._handle_control(data)
            return
        if kind == "ss2":
            self.terminal.single_shift_2()
            return
        if kind == "ss3":
            self.terminal.single_shift_3()
            return
        if kind == "esc":
            if not dispatch_escape(self.terminal, data):
                logger.debug("Unknown ESC: %r", data)
            return
        if kind in ("esc_charset", "esc_charset2"):
            if not handle_charset_escape(self.terminal, data):
                logger.debug("Unknown SCS: %r", data)
            return

        # Paired sequences
        if kind == "csi":
            dispatch_csi(self.terminal, data)
            return
        if kind == "osc":
            dispatch_osc(self.terminal, parse_string_sequence(data, "osc"))
            return
        if kind == "dcs":
            dispatch_dcs(self.terminal, parse_string_sequence(data, "dcs"))
            return
        if kind == "apc":
            logger.debug("APC: %r", data)
            return
        if kind == "pm":
            logger.debug("PM: %r", data)
            return
        if kind == "sos":
            logger.debug("SOS: %r", data)
            return

        logger.debug("Unknown kind: %s", kind)

    def _handle_control(self, ch: str) -> None:
        # ch is a single codepoint
        if ch == constants.BEL:
            self.terminal.bell()
        elif ch == constants.BS:
            self.terminal.backspace()
        elif ch == constants.HT:
            # real terminals use a tab stop table; simple next-8 for now
            next_tab = ((self.terminal.cursor_x // 8) + 1) * 8
            self.terminal.cursor_x = min(next_tab, self.terminal.width - 1)
        elif ch in (constants.LF, constants.VT, constants.FF):
            self.terminal.line_feed()
        elif ch == constants.CR:
            self.terminal.cursor_x = 0
        elif ch == constants.SO:
            self.terminal.current_charset = 1
        elif ch == constants.SI:
            self.terminal.current_charset = 0
        elif ch == constants.DEL:
            # DEL is a no-op (do not treat as backspace)
            pass

    def reset(self) -> None:
        self.buffer = ""
        self.pos = 0
        self.mode = None
