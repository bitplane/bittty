"""Core Parser class with state machine and sequence dispatching (fast state-specific scanners)."""

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

# -------------------------
# Unified 7-bit + 8-bit tokens (GROUND only)
# Order matters: specific before generic.
# -------------------------
GROUND_PATTERNS = {
    # Paired sequence starters
    "osc": r"(?:\x1b\]|\x9D)",
    "dcs": r"(?:\x1bP|\x90)",
    "apc": r"(?:\x1b_|\x9F)",
    "pm": r"(?:\x1b\^|\x9E)",
    "sos": r"(?:\x1bX|\x98)",
    "csi": r"(?:\x1b\[|\x9B)",
    # SCS (charset designation) MUST precede generic ESC minis
    "esc_charset": r"\x1b[()][A-Za-z0-9<>=@]",  # G0/G1
    "esc_charset2": r"\x1b[*+][A-Za-z0-9<>=@]",  # G2/G3
    # Singles / minis
    "ss2": r"(?:\x1bN|\x8E)",
    "ss3": r"(?:\x1bO|\x8F)",
    # Generic simple ESC minis (not starters for paired strings)
    # excludes [, ], P, _, ^, X, and ST (\)
    "esc": r"\x1b[^][P_^XO\\]",
    # C0/C1 controls except BEL/CAN/SUB/ESC (ESC handled via others; ESC alone should hit 'trail')
    "ctrl": r"[\x00-\x06\x08-\x17\x19\x1C-\x1F\x7F]",
    # Specials
    "bel": r"\x07",
    "cancel": r"[\x18\x1A]",  # CAN / SUB (abort current sequence if in one)
    # End-of-buffer guard: bare ESC or incomplete starter at buffer end
    "trail": r"(?:\x1b(?:[\[\]P_^X])?|\x90|\x9B|\x9D|\x9E|\x9F|\x98)\Z",
}


def _compile(name_to_pat: dict[str, str]) -> re.Pattern:
    return re.compile("|".join(f"(?P<{k}>{v})" for k, v in name_to_pat.items()))


# Ground scanner
GROUND_RE = _compile(GROUND_PATTERNS)

# CSI: only final byte or cancel. (No trail inside CSI; just wait for more.)
CSI_TERM_RE = re.compile(r"(?P<csi_final>[\x40-\x7E])|(?P<cancel>[\x18\x1A])")

# STRING terminators: allow ST or BEL for all string classes, plus cancel.
STR_TERM_RE = re.compile(r"(?P<st>(?:\x1b\\|\x9C))|(?P<bel>\x07)|(?P<cancel>[\x18\x1A])")

PAIRED = {"osc", "dcs", "apc", "pm", "sos", "csi"}
STANDALONES = {"ss2", "ss3", "esc", "esc_charset", "esc_charset2", "ctrl", "bel"}


@lru_cache(maxsize=300)
def parse_string_sequence(data: str, sequence_type: str) -> str:
    """Strip prefix and terminator for OSC/DCS/APC/PM/SOS."""
    if not data:
        return ""
    # Remove prefix (support both 7-bit ESC-prefixed and 8-bit C1)
    if sequence_type == "osc":
        content = data[1:] if data[:1] == "\x9d" else (data[2:] if data.startswith("\x1b]") else "")
    elif sequence_type == "dcs":
        content = data[1:] if data[:1] == "\x90" else (data[2:] if data.startswith("\x1bP") else "")
    elif sequence_type == "apc":
        content = data[1:] if data[:1] == "\x9f" else (data[2:] if data.startswith("\x1b_") else "")
    elif sequence_type == "pm":
        content = data[1:] if data[:1] == "\x9e" else (data[2:] if data.startswith("\x1b^") else "")
    elif sequence_type == "sos":
        content = data[1:] if data[:1] == "\x98" else (data[2:] if data.startswith("\x1bX") else "")
    else:
        return ""
    if not content:
        return ""

    # Strip terminator
    if content.endswith("\x1b\\"):
        return content[:-2]
    last = content[-1]
    if last == "\x9c" or last == "\x07":
        return content[:-1]
    return content


class Parser:
    """
    State machine: GROUND → (CSI | STRING[osc|dcs|apc|pm|sos]) → GROUND
    Uses small, state-specific scanners for speed.
    """

    def __init__(self, terminal: Terminal) -> None:
        self.terminal = terminal
        self.buffer = ""
        self.pos = 0
        self.mode: str | None = None  # None, 'csi', 'osc', 'dcs', 'apc', 'pm', 'sos'

        # kept for API compatibility
        self.escape_patterns = GROUND_PATTERNS.copy()
        self.tokenizer = GROUND_RE

        # bounds for current paired sequence
        self._seq_start = 0  # index where introducer starts
        self._scan_from = 0  # index just after introducer (for searching finals)

    def update_tokenizer(self) -> None:
        # API compat; nothing dynamic here
        self.tokenizer = GROUND_RE

    def update_pattern(self, key: str, pattern: str) -> None:
        # Rarely used; keep behavior if you mutate patterns externally
        self.escape_patterns[key] = pattern
        self.tokenizer = _compile(self.escape_patterns)

    # ---- internal helpers ----
    def _set_seq_bounds(self, start: int) -> None:
        """Set seq_start and scan_from based on 7-bit/8-bit introducer length."""
        self._seq_start = start
        b = self.buffer
        # 8-bit forms are single-char; 7-bit are ESC + one char
        if b[start] == "\x1b":
            self._scan_from = start + 2
        else:
            self._scan_from = start + 1

    # ---- main entry ----
    def feed(self, chunk: str) -> None:
        self.buffer += chunk

        while True:
            if self.mode is None:
                # ---- GROUND: scan for next token
                trail_start: int | None = None
                for m in self.tokenizer.finditer(self.buffer, self.pos):
                    kind = m.lastgroup
                    start, end = m.start(), m.end()

                    if kind == "trail":
                        trail_start = start
                        break

                    # flush preceding printables
                    if start > self.pos:
                        self.dispatch("print", self.buffer[self.pos : start])
                        self.pos = start

                    if kind in PAIRED:
                        # enter a paired sequence; keep starter in buffer
                        self.mode = kind
                        self._set_seq_bounds(start)
                        break

                    if kind == "cancel":
                        # CAN/SUB in ground: ignore
                        self.pos = end
                        continue

                    # Standalone controls/minis
                    self.dispatch(kind, self.buffer[start:end])
                    self.pos = end
                else:
                    # no more matches
                    if self.pos < len(self.buffer):
                        self.dispatch("print", self.buffer[self.pos :])
                        self.pos = len(self.buffer)

                # hit a trailing starter → leave it buffered for next chunk
                if trail_start is not None:
                    if self.pos < trail_start:
                        self.dispatch("print", self.buffer[self.pos : trail_start])
                        self.pos = trail_start
                    break  # wait for more data

                # if we entered a mode, handle it now
                if self.mode is None:
                    break

            if self.mode == "csi":
                # Find final or cancel, searching AFTER the introducer
                m = CSI_TERM_RE.search(self.buffer, self._scan_from)
                if not m:
                    # incomplete CSI, wait for more
                    break
                end = m.end()
                if m.lastgroup == "cancel":
                    # abort CSI
                    self.pos = end
                    self.mode = None
                    continue
                # dispatch full sequence from introducer to final
                self.dispatch("csi", self.buffer[self._seq_start : end])
                self.pos = end
                self.mode = None
                continue

            # STRING modes (OSC/DCS/APC/PM/SOS) — ST or BEL terminate; CAN/SUB cancels
            m = STR_TERM_RE.search(self.buffer, self._scan_from)
            if not m:
                # incomplete string, wait
                break
            end = m.end()
            if m.lastgroup == "cancel":
                # abort string
                self.pos = end
                self.mode = None
                continue
            # include from starter to ST/BEL
            self.dispatch(self.mode, self.buffer[self._seq_start : end])
            self.pos = end
            self.mode = None
            # loop to handle next token immediately

        # compact processed buffer
        if self.pos > 0:
            delta = self.pos
            self.buffer = self.buffer[self.pos :]
            self.pos = 0
            # if we were mid-sequence, keep bounds consistent after compaction
            if self.mode is not None and delta:
                self._seq_start = max(0, self._seq_start - delta)
                self._scan_from = max(0, self._scan_from - delta)

    # ---- dispatchers ----
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
            # TODO: proper tab stops; next-8 for now
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
        self._seq_start = 0
        self._scan_from = 0
