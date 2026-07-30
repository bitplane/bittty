"""Capability probing for the stdio terminal.

Ask the real outer terminal what it can do, then hand a TerminalCaps up to the
backend. Uses a DA1-terminated handshake: fire all the queries plus a Primary DA
request, then read until the (universally answered) DA reply arrives, so optional
queries that go unanswered never make us hang. Non-tty or timeout ⇒ env/config
caps only.

The probe measures colour and geometry facts plus the outer terminal's ambiguous-width
and grapheme-clustering behaviour. The board uses the latter two to keep its cell grid
aligned with the destination.
"""

from __future__ import annotations

import os
import re
import select
import time
from dataclasses import replace

from ..caps import TerminalCaps

# Response patterns:
#   OSC 11 ; rgb:RRRR/GGGG/BBBB   (background colour)
#   CSI 6 ; height ; width t      (cell size in pixels, reply to CSI 16 t)
#   CSI 4 ; height ; width t      (window size in pixels, reply to CSI 14 t)
#   CSI row ; column R             (cursor positions around measured text)
#   CSI ? 2027 ; state $ y         (Unicode Core mode state)
#   CSI ? ... c                   (Primary DA — the handshake terminator)
_BG = re.compile(r"\]11;rgb:([0-9a-fA-F]+)/([0-9a-fA-F]+)/([0-9a-fA-F]+)")
_CELL = re.compile(r"\[6;(\d+);(\d+)t")
_WINDOW = re.compile(r"\[4;(\d+);(\d+)t")
_CPR = re.compile(r"\[(\d+);(\d+)R")
_GRAPHEME_MODE = re.compile(r"\[\?2027;([0-4])\$y")
_DA1 = re.compile(r"\[\?[0-9;]*c")

# Measure U+00A7 SECTION SIGN (East Asian Width=A), then a complex ZWJ emoji
# whose grapheme width is 2 but whose legacy codepoint widths sum to more.
# Each measurement uses the already-cleared startup screen and cleans up after
# itself. Primary DA remains last so its reply terminates the handshake.
_WIDTH_QUERY = "\0337\033[1;1H\033[6n§\033[6n\033[1;1H\033[2K\0338"
_GRAPHEME_SAMPLE = "⛓️‍💥"
_GRAPHEME_WIDTH_QUERY = f"\0337\033[1;1H\033[6n{_GRAPHEME_SAMPLE}\033[6n\033[1;1H\033[2K\0338"
PROBE_QUERY = _WIDTH_QUERY + _GRAPHEME_WIDTH_QUERY + "\033]11;?\007\033[16t\033[14t\033[?2027$p\033[c"


def color_depth_from_env(env) -> str:
    """Best-effort colour depth from COLORTERM / TERM (no query exists for this)."""
    if env.get("COLORTERM", "") in ("truecolor", "24bit"):
        return "truecolor"
    term = env.get("TERM", "")
    if "256color" in term:
        return "256"
    if term in ("", "dumb"):
        return "unknown"
    return "16"


def _high_byte(hex_channel: str) -> int:
    """The 8-bit value of a terminal colour channel reported as 1-4 hex digits."""
    return int(hex_channel[:2].ljust(2, "0"), 16)


def _cursor_delta(positions: list[tuple[int, int]], offset: int) -> int | None:
    """Measured cursor advance for one before/after CPR pair."""
    if len(positions) < offset + 2:
        return None
    (before_row, before_col), (after_row, after_col) = positions[offset : offset + 2]
    if before_row != after_row:
        return None
    return after_col - before_col


def parse_probe_replies(buf: str, env) -> TerminalCaps:
    """Build TerminalCaps from a probe-reply buffer, unioned with env (probe wins)."""
    background = None
    if (m := _BG.search(buf)) is not None:
        background = (_high_byte(m.group(1)), _high_byte(m.group(2)), _high_byte(m.group(3)))
    cell_px = None
    if (m := _CELL.search(buf)) is not None:  # reply is height;width
        cell_px = (int(m.group(2)), int(m.group(1)))
    window_px = None
    if (m := _WINDOW.search(buf)) is not None:
        window_px = (int(m.group(2)), int(m.group(1)))
    ambiguous_width = None
    positions = [(int(m.group(1)), int(m.group(2))) for m in _CPR.finditer(buf)]
    if (delta := _cursor_delta(positions, 0)) in (1, 2):
        ambiguous_width = delta
    grapheme_width = _cursor_delta(positions, 2)
    grapheme_mode = None
    if (m := _GRAPHEME_MODE.search(buf)) is not None:
        grapheme_mode = {
            "0": "unsupported",
            "1": "set",
            "2": "reset",
            "3": "permanently-set",
            "4": "permanently-reset",
        }[m.group(1)]
    if grapheme_mode in (None, "unsupported") and grapheme_width == 2:
        # tmux and similar intermediaries may implement always-on grapheme
        # clustering without implementing mode 2027 itself.
        grapheme_mode = "permanently-set"
    return TerminalCaps(
        color_depth=color_depth_from_env(env),
        cell_px=cell_px,
        window_px=window_px,
        background=background,
        ambiguous_width=ambiguous_width,
        grapheme_mode=grapheme_mode,
    )


def probe_caps(stdin_fd, write, env=None, timeout: float = 0.5) -> TerminalCaps:
    """Query the real terminal and return TerminalCaps; env-only on a non-tty/timeout.

    `write` is a callable that writes a str to the outer terminal (and flushes).
    """
    env = os.environ if env is None else env
    if stdin_fd is None or not os.isatty(stdin_fd):
        return parse_probe_replies("", env)

    write(PROBE_QUERY)
    buf = ""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        readable, _, _ = select.select([stdin_fd], [], [], max(0.0, end - time.monotonic()))
        if not readable:
            break
        chunk = os.read(stdin_fd, 4096)
        if not chunk:
            break
        buf += chunk.decode("utf-8", errors="replace")
        if _DA1.search(buf):  # the DA reply terminates the handshake
            break
    caps = parse_probe_replies(buf, env)
    if caps.grapheme_mode is None:
        # The query was sent on a real tty. No reply before the DA terminator
        # (or timeout) is a conservative "not supported", not "no opinion".
        caps = replace(caps, grapheme_mode="unsupported")
    return caps
