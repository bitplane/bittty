"""Core Parser class with state machine and sequence dispatching (fast state-specific scanners)."""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..operations import OperationSink

from ..operations import Operation, control_name
from .csi import parse_csi_operation
from .dcs import parse_dcs_operation
from .escape import parse_charset_operation, parse_escape_operation, parse_hash_operation
from .osc import parse_osc_operation

logger = logging.getLogger(__name__)

# -------------------------
# Unified 7-bit + 8-bit tokens (GROUND only)
# Order matters: specific before generic.
# -------------------------
GROUND_PATTERNS = {
    # A run of printable text as one match. Without this the engine fails the
    # whole alternation at every printable position; with it, bulk text is one
    # C-speed class scan per run. Excludes C0, DEL, and the C1 range (escape
    # starters and controls); unmatched C1 strays still print via the gap flush.
    "text": r"[^\x00-\x1F\x7F-\x9F]+",
    # A complete CSI in one match (params, intermediates, final — the ECMA-48 byte
    # ranges are regular). Matching whole sequences here keeps the scanner in a
    # single finditer pass; the old starter below is the fallback for incomplete
    # or malformed sequences and drops into the mode machinery.
    "csi_seq": r"(?:\x1b\[|\x9B)[0-9;:?<=>]*[ -/]*[@-~]",
    # CR+LF fused into one token: a scroll flood is 30k of these pairs, and one
    # pipeline trip per pair halves its dispatch cost.
    "crlf": r"\r\n",
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
    # ESC # n — line size / alignment (DECALN is ESC # 8). Before generic ESC minis.
    "esc_hash": r"\x1b#[0-9]",
    # ESC % @ / ESC % G — select coding system (UTF-8). Before generic ESC minis.
    "esc_percent": r"\x1b%[@G]",
    # ESC SP F/G — C1 transmission (S7C1T/S8C1T); ESC SP L/M/N — ANSI conformance level.
    "esc_space": r"\x1b\x20[FGLMN]",
    # End-of-buffer guard: bare ESC, an incomplete paired starter, or an incomplete
    # two-char prefix ( ) * + # % SP at buffer end. MUST precede the generic 'esc'
    # alternative, or a chunk split after e.g. ESC ( is consumed as an ESC mini and
    # the designator that arrives next chunk prints as text.
    "trail": r"(?:\x1b(?:[\[\]P_^X()*+#%\x20])?|\x90|\x9B|\x9D|\x9E|\x9F|\x98)\Z",
    # Generic simple ESC minis (not starters for paired strings)
    # excludes [, ], P, _, ^, X, and ST (\)
    "esc": r"\x1b[^][P_^XO\\]",
    # C0/C1 controls except BEL/CAN/SUB/ESC (ESC handled via others; ESC alone should hit 'trail')
    "ctrl": r"[\x00-\x06\x08-\x17\x19\x1C-\x1F\x7F]",
    # Raw 8-bit C1 format/area controls: IND NEL HTS RI SPA EPA.
    "c1_ctrl": r"[\x84\x85\x88\x8d\x96\x97]",
    # Specials
    "bel": r"\x07",
    "cancel": r"[\x18\x1A]",  # CAN / SUB (abort current sequence if in one)
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

# Raw 8-bit C1 format/area controls -> their operation names (same as the 7-bit ESC forms).
_C1_CTRL_NAMES = {"\x84": "IND", "\x85": "NEL", "\x88": "HTS", "\x8d": "RI", "\x96": "SPA", "\x97": "EPA"}

# One shared frozen Operation per C0 control (a scroll flood is mostly CR/LF).
_BEL_OP = Operation("C0_BEL", raw="\x07")
_CRLF_OP = Operation("C0_CRLF", raw="\r\n")
_CTRL_OPS: dict[str, Operation] = {}
# ESC SP F/G = 7/8-bit C1 transmission; ESC SP L/M/N = ANSI conformance level 1/2/3.
_ESC_SPACE_OPS = {
    "F": ("S7C1T", ()),
    "G": ("S8C1T", ()),
    "L": ("ANSI_LEVEL", (1,)),
    "M": ("ANSI_LEVEL", (2,)),
    "N": ("ANSI_LEVEL", (3,)),
}


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

    def __init__(self, sink: OperationSink) -> None:
        self.sink = sink
        self.buffer = ""
        self.pos = 0
        self.mode: str | None = None  # None, 'csi', 'osc', 'dcs', 'apc', 'pm', 'sos'

        # bounds for current paired sequence
        self._seq_start = 0  # index where introducer starts
        self._scan_from = 0  # index just after introducer (for searching finals)

        # Fast dispatch: when the sink is a device board it exposes its handler
        # registry; hot tokens then skip the emit/handle_operation frames and a
        # repeated CSI costs one memo hit and one call. Sinks without a registry
        # (recording sinks in tests) take the plain handle_operation path.
        self._handle = sink.handle_operation
        registry = getattr(sink, "registry", None)
        self._registry = registry
        self._print_h = registry.get("PRINT") if registry is not None else None
        self._crlf_h = registry.get("C0_CRLF") if registry is not None else None
        self._csi_memo: dict = {}

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

        handle = self._handle
        print_h = self._print_h or handle
        crlf_h = self._crlf_h
        csi_memo = self._csi_memo

        while True:
            if self.mode is None:
                # ---- GROUND: scan for next token
                trail_start: int | None = None
                for m in GROUND_RE.finditer(self.buffer, self.pos):
                    kind = m.lastgroup
                    start, end = m.span()

                    if kind == "trail":
                        trail_start = start
                        break

                    # flush preceding printables
                    if start > self.pos:
                        text = self.buffer[self.pos : start]
                        print_h(Operation("PRINT", (text,), text))
                        self.pos = start

                    # Hot one-shot tokens: dispatch inline and stay in this
                    # finditer pass (no mode transition, no scanner restart).
                    if kind == "text":
                        text = m.group()
                        print_h(Operation("PRINT", (text,), text))
                        self.pos = end
                        continue
                    if kind == "csi_seq":
                        raw = m.group()
                        entry = csi_memo.get(raw)
                        if entry is None:
                            op = parse_csi_operation(raw) or Operation("CSI", raw=raw)
                            h = self._registry.get(op.name) if self._registry is not None else None
                            entry = (h or handle, op)
                            if len(csi_memo) < 4096:  # bounded like the parse cache
                                csi_memo[raw] = entry
                        entry[0](entry[1])
                        self.pos = end
                        continue
                    if kind == "crlf":
                        if crlf_h is not None:
                            crlf_h(_CRLF_OP)
                        else:
                            handle(_CRLF_OP)
                        self.pos = end
                        continue

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

            # Linux console fixed-length palette forms hijack the OSC introducer but
            # carry no ST/BEL terminator: ESC ] P nrrggbb (10 chars) and ESC ] R.
            if self.mode == "osc":
                head = self.buffer[self._scan_from] if self._scan_from < len(self.buffer) else ""
                if head == "R":
                    end = self._scan_from + 1
                    self.emit(Operation("LINUX_PALETTE_RESET", (), self.buffer[self._seq_start : end]))
                    self.pos = end
                    self.mode = None
                    continue
                if head == "P":
                    if len(self.buffer) < self._scan_from + 8:
                        break  # ESC ] P + 7 hex not all here yet — wait for the next chunk
                    end = self._scan_from + 8
                    payload = self.buffer[self._scan_from + 1 : end]
                    self.emit(Operation("LINUX_PALETTE_SET", (payload,), self.buffer[self._seq_start : end]))
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
            self.emit(Operation("PRINT", (data,), data))
            return

        # Standalones
        if kind == "bel":
            self.emit(_BEL_OP)
            return
        if kind == "ctrl":
            op = _CTRL_OPS.get(data)
            if op is None:
                op = _CTRL_OPS[data] = Operation(control_name(data), raw=data)
            self.emit(op)
            return
        if kind == "ss2":
            self.emit(Operation("SS2", raw=data))
            return
        if kind == "ss3":
            self.emit(Operation("SS3", raw=data))
            return
        if kind == "esc":
            self.emit(parse_escape_operation(data) or Operation("ESC", raw=data))
            return
        if kind in ("esc_charset", "esc_charset2"):
            self.emit(parse_charset_operation(data) or Operation("SCS", raw=data))
            return
        if kind == "esc_hash":
            self.emit(parse_hash_operation(data) or Operation("ESC_HASH", (data[2],), data))
            return
        if kind == "esc_percent":
            # ESC % @ / ESC % G select the coding system; bittty is always Unicode,
            # so this is consumed and ignored (rather than leaking the final byte).
            return
        if kind == "c1_ctrl":
            self.emit(Operation(_C1_CTRL_NAMES[data], raw=data))
            return
        if kind == "esc_space":
            name, args = _ESC_SPACE_OPS[data[2]]
            self.emit(Operation(name, args, data))
            return

        # Paired sequences
        if kind == "csi":
            self.emit(parse_csi_operation(data) or Operation("CSI", raw=data))
            return
        if kind == "osc":
            self.emit(parse_osc_operation(parse_string_sequence(data, "osc"), data) or Operation("OSC", raw=data))
            return
        if kind == "dcs":
            self.emit(parse_dcs_operation(parse_string_sequence(data, "dcs"), data))
            return
        if kind == "apc":
            self.emit(Operation("APC", (parse_string_sequence(data, "apc"),), data))
            return
        if kind == "pm":
            self.emit(Operation("PM", (parse_string_sequence(data, "pm"),), data))
            return
        if kind == "sos":
            self.emit(Operation("SOS", (parse_string_sequence(data, "sos"),), data))
            return

        logger.debug("Unknown kind: %s", kind)

    def emit(self, operation: Operation) -> None:
        self.sink.handle_operation(operation)

    def reset(self) -> None:
        self.buffer = ""
        self.pos = 0
        self.mode = None
        self._seq_start = 0
        self._scan_from = 0
